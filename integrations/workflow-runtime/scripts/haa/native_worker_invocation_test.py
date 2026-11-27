from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import unittest

from scripts.haa.native_worker_invocation import native_worker_invocation
from scripts.haa.protected_supervisor import SupervisorError


class NativeInvocationTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name).resolve()
        target=base/"target";target.mkdir();(target/"a.txt").write_text("before")
        scratch=base/"scratch";scratch.mkdir()
        install=base/"install";(install/"adapters").mkdir(parents=True)
        runner=install/"adapters/run_local_task.py";runner.touch()
        self.layout=SimpleNamespace(target=target,scratch=scratch,install=install,worker_uid=502)
        self.task=SimpleNamespace(repository="krukmat/dubbridge",repo_root=target)
        self.authority=Mock();self.authority._lock=RLock()
        self.authority.scope=SimpleNamespace(task=self.task,lease_id="l")
        self.authority.leases.load.return_value=SimpleNamespace(allowed_paths=("a.txt",))
        self.card=SimpleNamespace(task_id="t",rri=35)
        self.pin=patch("scripts.haa.native_worker_invocation.checked_bound_card",return_value=self.card)
        self.pin.start();self.addCleanup(self.pin.stop)
        self.args=dict(layout=self.layout,authority=self.authority,python=Path(sys.executable).resolve(),
            socket_path=base/"ipc.sock",runner=runner,input_file=scratch/"card",
            output_file=scratch/"out",worktree=scratch/"repo",paths=("a.txt",))

    def test_fixed_native_worker_argv(self):
        call=native_worker_invocation(**self.args)
        self.assertIn("-I",call.argv);self.assertIn("-B",call.argv)
        self.assertEqual(call.argv[-2:],("--path","a.txt"))
        self.assertIn("502",call.argv)
        self.assertEqual(call.cwd,self.layout.scratch/"repo")

    def test_scope_and_unstaged_runner_denied(self):
        for changed in ({"paths":("outside.txt",)},{"runner":self.layout.scratch/"run_local_task.py"},
                        {"input_file":self.layout.target/"card"}):
            with self.subTest(changed=changed),self.assertRaises(SupervisorError):
                native_worker_invocation(**{**self.args,**changed})
