from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from threading import RLock
import subprocess
import unittest

from scripts.haa.contracts import digest_json
from scripts.haa.protected_commit import ProtectedCommit, CommitError, VerificationResult
from scripts.haa.volatile_authority import VolatileLeaseStore


class ProtectedCommitTest(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name).resolve()
        self.root=base/"repo";self.root.mkdir()
        self.state=base/"state";self.state.mkdir(mode=0o700)
        self.git("init","-b","candidate")
        self.git("config","user.name","test")
        self.git("config","user.email","test@example.invalid")
        (self.root/"a.txt").write_text("original")
        (self.root/"b.txt").write_text("other")
        self.git("add","a.txt","b.txt")
        self.git("commit","-m","base")
        self.parent=self.git("rev-parse","HEAD")
        (self.root/"a.txt").write_text("candidate")
        self.authority=Mock()
        self.authority._lock=RLock()
        self.authority.leases=Mock(spec=VolatileLeaseStore)
        self.authority.leases.load.return_value=SimpleNamespace(allowed_paths=("a.txt",))
        self.authority.scope=SimpleNamespace(task=SimpleNamespace(repo_root=self.root,session_id="s"),lease_id="l")
        self.verifier=Mock()
        self.verifier.verify.side_effect=lambda c,cmd: VerificationResult(c.tree,c.session,c.commands_digest,(0,),digest_json({"test":"pass"}))
        self.adapter=ProtectedCommit(self.authority,state=self.state,verifier=self.verifier)
        self.adapter._commands=lambda: (("test-command",),)

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.root),*args],stderr=subprocess.DEVNULL,text=True).strip()

    def test_commit_contains_only_authorized_tree(self):
        (self.root/"b.txt").write_text("unrelated")
        result=self.adapter.commit(("a.txt",))
        self.assertEqual(self.git("show","HEAD:a.txt"),"candidate")
        self.assertEqual(self.git("show","HEAD:b.txt"),"other")
        self.assertEqual(self.git("rev-parse","HEAD^"),self.parent)
        self.assertEqual(result["status"],"COMMITTED_LOCAL")
        self.assertEqual(self.git("diff","--cached","--name-only"),"")
        self.assertEqual(self.git("diff","--name-only"),"b.txt")

    def test_broker_digest_required_for_candidate(self):
        self.adapter.accepted_edit=("a.txt","0"*64)
        with self.assertRaisesRegex(CommitError,"BROKER_ACCEPTED_EDIT_MISMATCH"):
            self.adapter.commit(("a.txt",))
        self.assertEqual(self.git("rev-parse","HEAD"),self.parent)
        self.verifier.verify.assert_not_called()

    def test_existing_staged_changes_block(self):
        (self.root/"b.txt").write_text("staged")
        self.git("add","b.txt")
        with self.assertRaisesRegex(CommitError,"PREEXISTING_STAGED_CHANGES"):
            self.adapter.commit(("a.txt",))
        self.assertEqual(self.git("rev-parse","HEAD"),self.parent)
        self.verifier.verify.assert_not_called()

    def test_outside_scope_no_ref_update(self):
        with self.assertRaises(CommitError):
            self.adapter.commit(("b.txt",))
        self.assertEqual(self.git("rev-parse","HEAD"),self.parent)
        self.verifier.verify.assert_not_called()

    def test_wrong_tree_verification_denies(self):
        self.verifier.verify.side_effect=None
        self.verifier.verify.return_value=VerificationResult("x","s","wrong",(0,),digest_json({"test":"pass"}))
        with self.assertRaisesRegex(CommitError,"VERIFICATION_NOT_BOUND"):
            self.adapter.commit(("a.txt",))
        self.assertEqual(self.git("rev-parse","HEAD"),self.parent)

    def test_changed_preimage_during_tests_denies(self):
        def drift(c,cmd):
            (self.root/"a.txt").write_text("changed")
            return VerificationResult(c.tree,c.session,c.commands_digest,(0,),digest_json({"test":"pass"}))
        self.verifier.verify.side_effect=drift
        with self.assertRaisesRegex(CommitError,"CANDIDATE_CHANGED"):
            self.adapter.commit(("a.txt",))
        self.assertEqual(self.git("rev-parse","HEAD"),self.parent)
