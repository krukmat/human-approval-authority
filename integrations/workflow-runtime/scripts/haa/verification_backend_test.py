from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import unittest
from unittest.mock import Mock,patch

from scripts.haa.contracts import digest_json
from scripts.haa.protected_commit import CandidateTree
from scripts.haa.verification_backend import (
    ExactTreeVerifier, VerificationIdentity, VerificationError, _export,
)


class ExactTreeVerifierTest(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name).resolve()
        self.repo=base/"repo"; self.repo.mkdir()
        self.exports=base/"exports"; self.exports.mkdir(mode=0o750)
        self.git("init","-b","candidate")
        self.git("config","user.name","fixture")
        self.git("config","user.email","fixture@example.invalid")
        (self.repo/"a.txt").write_bytes(b"committed bytes")
        self.git("add","a.txt");self.git("commit","-m","fixture")
        self.tree=self.git("rev-parse","HEAD^{tree}")
        self.commands=(("/usr/bin/true",),)
        self.candidate=CandidateTree(self.git("rev-parse","HEAD"),"refs/heads/candidate",
            self.tree,("a.txt",),"session",digest_json([list(c) for c in self.commands]))
        self.identity=VerificationIdentity(os.geteuid(),os.geteuid()+1,os.geteuid()+2,
                                          self.exports.stat().st_gid)
        self.launcher=Mock()
        # Tests intentionally do not simulate an actual UID separation PASS.
        check=patch.object(VerificationIdentity,"check");check.start();self.addCleanup(check.stop)
        self.verifier=ExactTreeVerifier(repo=self.repo,exports=self.exports,identity=self.identity,
                                       launcher=self.launcher)

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.repo),*args],
            stderr=subprocess.DEVNULL,text=True).strip()

    def test_reads_git_tree_not_dirty_worktree(self):
        (self.repo/"a.txt").write_text("untrusted working copy")
        def launch(argv,*,source,identity,timeout):
            self.assertEqual((source/"a.txt").read_bytes(),b"committed bytes")
            self.assertEqual((source/"a.txt").stat().st_mode & 0o777,0o440)
            return 0
        self.launcher.run.side_effect=launch
        result=self.verifier.verify(self.candidate,self.commands)
        self.assertEqual(result.exit_codes,(0,))
        self.assertEqual(result.tree,self.tree)
        self.assertEqual(list(self.exports.iterdir()),[])

    def test_wrong_argv_denied_before_launch(self):
        with self.assertRaisesRegex(VerificationError,"COMMAND_BINDING"):
            self.verifier.verify(self.candidate,(("wrong",),))
        self.launcher.run.assert_not_called()

    def test_timeout_blocks_future_runs(self):
        self.launcher.run.side_effect=TimeoutError
        with self.assertRaises(TimeoutError):
            self.verifier.verify(self.candidate,self.commands)
        with self.assertRaisesRegex(VerificationError,"OPERATOR_RECONCILIATION"):
            self.verifier.verify(self.candidate,self.commands)
        self.launcher.run.assert_called_once()

    def test_nonzero_exit_not_transformed_to_pass(self):
        self.launcher.run.return_value=7
        self.assertEqual(self.verifier.verify(self.candidate,self.commands).exit_codes,(7,))

    def test_internal_symlink_preserved(self):
        (self.repo/"link").symlink_to("a.txt")
        self.git("add","link");self.git("commit","-m","link")
        dest=self.exports/"dest";dest.mkdir()
        _export(self.repo,self.git("rev-parse","HEAD^{tree}"),dest,self.identity.verifier_gid)
        self.assertTrue((dest/"link").is_symlink())
        self.assertEqual(os.readlink(dest/"link"),"a.txt")
        self.assertEqual((dest/"link").read_bytes(),b"committed bytes")

    def test_external_symlink_denied(self):
        (self.repo/"link").symlink_to("../outside")
        self.git("add","link");self.git("commit","-m","link")
        dest=self.exports/"dest";dest.mkdir()
        with self.assertRaisesRegex(VerificationError,"SYMLINK_ESCAPES_TREE"):
            _export(self.repo,self.git("rev-parse","HEAD^{tree}"),dest,self.identity.verifier_gid)


class VerificationIdentityTest(unittest.TestCase):
    def test_same_agent_and_verifier_rejected(self):
        with self.assertRaisesRegex(VerificationError,"IDENTITY_NOT_SEPARATED"):
            VerificationIdentity(501,502,502,503).check()
