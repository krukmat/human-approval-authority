from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from scripts.haa.protected_supervisor import (
    ProtectedSupervisor,SupervisorError,worker_invocation,
)
from scripts.haa.protected_session import ProtectedSession
from scripts.haa.verification_backend import ExactTreeVerifier


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        root=Path(t.name).resolve()
        self.layout=SimpleNamespace(target=root/"target",scratch=root/"scratch",
                                    install=root/"code")
        self.plan=Mock()
        self.plan.read_snapshot.return_value.workflow_state="ACTIVE"
        verifier=Mock(spec=ExactTreeVerifier);verifier.repo=self.layout.target
        self.verifier=verifier
        with patch("scripts.haa.protected_supervisor.PlanCloseController"):
            self.supervisor=ProtectedSupervisor(layout=self.layout,approved=Mock(),
                plan=self.plan,verifier=verifier,plan_validation=Mock())
        self.session=Mock(spec=ProtectedSession)
        self.session.layout=self.layout
        self.session._accepted_edit=("README.md","a"*64)

    def test_only_accepted_path_published(self):
        self.supervisor.begin(self.session)
        with self.assertRaisesRegex(SupervisorError,"NOT_QUIESCENT"):
            self.supervisor.assert_no_active_tasks()
        listener=Mock()
        self.supervisor.execute(listener)
        self.session.activate.assert_called_once()
        self.session.complete_task.assert_called_once_with(plan=self.plan,
            verifier=self.verifier,paths=("README.md",))
        listener.close.assert_called_once()
        self.supervisor.assert_no_active_tasks()

    def test_failure_latches_and_closes(self):
        self.supervisor.begin(self.session)
        self.session.serve_worker.side_effect=RuntimeError("fixture")
        with self.assertRaises(RuntimeError):
            self.supervisor.execute(Mock())
        self.session.close.assert_called_once()
        with self.assertRaisesRegex(SupervisorError,"NOT_QUIESCENT"):
            self.supervisor.assert_no_active_tasks()

    def test_worker_fixed_argv_and_path_scope(self):
        scratch=self.layout.scratch
        args=dict(layout=self.layout,python=Path("/usr/bin/python3").resolve(),
            socket_path=Path("/tmp/broker.sock"),card=scratch/"card.json",
            output=scratch/"out.json",path="README.md",worktree=scratch/"repo")
        invocation=worker_invocation(**args)
        self.assertEqual(invocation.cwd,scratch/"repo")
        self.assertIn("-I",invocation.argv)
        self.assertEqual(invocation.argv[-2:],("--path","README.md"))
        with self.assertRaisesRegex(SupervisorError,"OUTSIDE_SCRATCH"):
            worker_invocation(**{**args,"card":self.layout.target/"card.json"})
