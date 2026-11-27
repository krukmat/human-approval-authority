from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import subprocess
import unittest

from scripts.haa.submit_batch import collect


class SubmitBatchTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.git("init","-b","candidate")
        self.git("config","user.name","fixture")
        self.git("config","user.email","fixture@example.invalid")
        for p in ("a.txt","b.txt"):
            (self.root/p).write_text("before")
        self.git("add",".");self.git("commit","-m","base")
        for p in ("a.txt","b.txt"):
            (self.root/p).write_text("after")

    def git(self,*argv):
        return subprocess.check_output(["git","-C",str(self.root),*argv],
            stderr=subprocess.DEVNULL,text=True).strip()

    def test_collect_exact_complete_replacement_set(self):
        records=collect(self.root,["b.txt","a.txt"])
        self.assertEqual([r["path"] for r in records],["a.txt","b.txt"])
        self.assertTrue(all(r["before_sha256"]==sha256(b"before").hexdigest()
                            and r["content"]=="after" for r in records))

    def test_omitted_path_and_untracked_denied(self):
        with self.assertRaisesRegex(ValueError,"CHANGE_SET_MISMATCH"):
            collect(self.root,["a.txt"])
        (self.root/"new.txt").write_text("new")
        with self.assertRaisesRegex(ValueError,"UNTRACKED"):
            collect(self.root,["a.txt","b.txt"])

    def test_staged_changes_denied(self):
        self.git("add","a.txt")
        with self.assertRaisesRegex(ValueError,"STAGED"):
            collect(self.root,["a.txt","b.txt"])
