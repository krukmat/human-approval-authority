from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch
import os
import subprocess
import unittest

from scripts.haa.batch_commit import BatchCommit, parse_batch
from scripts.haa.contracts import digest_json
from scripts.haa.protected_broker import WorkerBroker, BrokerError
from scripts.haa.protected_commit import CommitError, VerificationResult
from scripts.haa.volatile_authority import VolatileLeaseStore


def replacement(path, before="before", after="after"):
    return {"path": path, "before_sha256": sha256(before.encode()).hexdigest(), "content": after}


class BatchCommitTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        base=Path(tmp.name).resolve()
        self.root=base/"repo"; self.root.mkdir()
        self.state=base/"state"; self.state.mkdir(mode=0o700)
        self.git("init","-b","candidate")
        self.git("config","user.name","fixture")
        self.git("config","user.email","fixture@example.invalid")
        for p in ("a.txt","b.txt","card.json","policy.md"):
            (self.root/p).write_text("before")
        self.git("add","."); self.git("commit","-m","base")
        self.head=self.git("rev-parse","HEAD")
        self.authority=Mock(); self.authority._lock=RLock()
        self.authority.leases=Mock(spec=VolatileLeaseStore)
        self.authority.leases.load.return_value=SimpleNamespace(
            allowed_paths=("a.txt","b.txt","card.json","policy.md","missing.txt"),
            base_commit_sha=self.head)
        self.authority.scope=SimpleNamespace(lease_id="l",task=SimpleNamespace(
            repo_root=self.root,session_id="s",card_path=self.root/"card.json",
            policy_pin=SimpleNamespace(sources=(("policy.md","p"),))))
        self.verifier=Mock()
        self.verifier.verify.side_effect=self.verify
        self.proposal=parse_batch([replacement("b.txt"),replacement("a.txt")])

    def git(self,*argv):
        return subprocess.check_output(["git","-C",str(self.root),*argv],
            stderr=subprocess.DEVNULL,text=True).strip()

    def verify(self,candidate,commands):
        for p in candidate.paths:
            self.assertEqual((self.root/p).read_text(),"before")
            self.assertEqual(self.git("show",candidate.tree+":"+p),"after")
        return VerificationResult(candidate.tree,candidate.session,candidate.commands_digest,
                                  (0,),digest_json("fixture"))

    def adapter(self,proposal=None):
        c=BatchCommit(self.authority,state=self.state,verifier=self.verifier,
                      proposal=proposal or self.proposal)
        c._commands=lambda: (("/usr/bin/true",),)
        return c

    def assert_pristine(self):
        self.assertEqual(self.git("rev-parse","HEAD"),self.head)
        self.assertEqual((self.root/"a.txt").read_text(),"before")
        self.assertEqual((self.root/"b.txt").read_text(),"before")

    def test_batch_verified_before_publication(self):
        c=self.adapter()
        result=c.commit(self.proposal.paths)
        self.assertEqual(result["status"],"COMMITTED_LOCAL")
        self.assertEqual(self.git("rev-parse","HEAD^"),self.head)
        self.assertEqual(self.git("show","HEAD:a.txt"),"after")
        self.assertEqual(self.git("show","HEAD:b.txt"),"after")
        self.assertEqual(self.git("status","--porcelain"),"")
        with self.assertRaisesRegex(CommitError,"ALREADY_ATTEMPTED"):
            c.commit(self.proposal.paths)

    def test_bad_preimage_blocks_entire_batch(self):
        p=parse_batch([replacement("a.txt"),replacement("b.txt","stale")])
        with self.assertRaisesRegex(CommitError,"STALE_OR_DIRTY"):
            self.adapter(p).commit(p.paths)
        self.assert_pristine()
        self.verifier.verify.assert_not_called()

    def test_untracked_or_pinned_path_blocks_entire_batch(self):
        for path in ("missing.txt","card.json","policy.md","outside.txt"):
            p=parse_batch([replacement("a.txt"),replacement(path)])
            with self.subTest(path=path),self.assertRaisesRegex(CommitError,"OUTSIDE_TRACKED_SCOPE"):
                self.adapter(p).commit(p.paths)
            self.assert_pristine()
        self.verifier.verify.assert_not_called()

    def test_verifier_failure_leaves_checkout_and_ref_unchanged(self):
        self.verifier.verify.side_effect=lambda c,cmd: VerificationResult(
            c.tree,c.session,c.commands_digest,(1,),digest_json("failed"))
        with self.assertRaisesRegex(CommitError,"VERIFICATION_NOT_BOUND"):
            self.adapter().commit(self.proposal.paths)
        self.assert_pristine()

    def test_revocation_after_verification_denies_before_any_write(self):
        def revoke(c,cmd):
            result=self.verify(c,cmd)
            self.authority._check.side_effect=RuntimeError("revoked")
            return result
        self.verifier.verify.side_effect=revoke
        with self.assertRaisesRegex(RuntimeError,"revoked"):
            self.adapter().commit(self.proposal.paths)
        self.assert_pristine()

    def test_mid_publication_failure_no_ref_update_no_retry(self):
        from scripts.haa.protected_broker import _replace_existing
        c=self.adapter()
        def effect(root,path,before,content):
            if path=="b.txt":
                raise OSError("fixture failure")
            return _replace_existing(root,path,before,content)
        with patch("scripts.haa.batch_commit._replace_existing",side_effect=effect):
            with self.assertRaises(OSError):
                c.commit(self.proposal.paths)
        self.assertEqual(self.git("rev-parse","HEAD"),self.head)
        self.assertEqual((self.root/"a.txt").read_text(),"after")
        self.assertEqual((self.root/"b.txt").read_text(),"before")
        with self.assertRaisesRegex(CommitError,"ALREADY_ATTEMPTED"):
            c.commit(self.proposal.paths)

    def test_broker_buffers_batch_without_mutating_target(self):
        broker=WorkerBroker(self.authority,worker_uid=os.geteuid()+1)
        uid=broker.worker_uid
        window=broker.dispatch(uid,{"op":"status"})["window"]
        msg={"op":"replace_batch","window":window,
             "changes":[replacement("b.txt"),replacement("a.txt")]}
        with self.assertRaises(BrokerError):
            broker.dispatch(uid+1,msg)
        self.assertEqual(broker.dispatch(uid,msg)["status"],"BATCH_ACCEPTED")
        self.assertEqual(broker.seal().paths,("a.txt","b.txt"))
        self.assert_pristine()
        with self.assertRaisesRegex(BrokerError,"WINDOW_CLOSED"):
            broker.dispatch(uid,msg)

    def test_parser_rejects_ambiguity_and_privilege_expansion(self):
        for changes in ([],[replacement("../escape")],[replacement(".GIT/config")],
                        [replacement("a.txt"),replacement("A.txt")],
                        [{**replacement("a.txt"),"op":"delete"}],
                        [replacement("a.txt","same","same")]):
            with self.subTest(changes=changes),self.assertRaises(CommitError):
                parse_batch(changes)
