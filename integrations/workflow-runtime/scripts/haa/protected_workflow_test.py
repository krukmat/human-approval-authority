from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import RLock
from unittest.mock import Mock, patch
import unittest

from scripts.haa.contracts import digest_json
from scripts.haa.plan_closure import ClosureError, PlanSnapshot
from scripts.haa.protected_commit import ProtectedCommit
from scripts.haa.protected_plan import ProtectedPlanJournal
from scripts.haa.protected_workflow import ProtectedWorkflow


class ProtectedWorkflowTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name).resolve()
        self.plan=ProtectedPlanJournal.initialize(root, signing_key=b"K"*32,
            repository="example/workflow-fixture",snapshot=PlanSnapshot("ACTIVE","p","v1",
                ("t",),(),(),(),{"status":"PENDING"},()))
        self.adapter=Mock(spec=ProtectedCommit)
        self.adapter.authority=Mock()
        self.adapter.authority._lock=RLock()
        self.adapter.authority.scope.task=SimpleNamespace(repo_root=root,
            repository="example/workflow-fixture",session_id="test-session")
        self.adapter.commit.return_value={"status":"COMMITTED_LOCAL","commit":"a"*40,
            "tree":"b"*40,"evidenceDigest":digest_json({"fixture":"PASS"})}
        self.adapter._sha.return_value="a"*40
        self.adapter._git.return_value=b""
        self.card=SimpleNamespace(plan="docs/plan/p.md",task_id="t")
        self.workflow=ProtectedWorkflow(commit_adapter=self.adapter,plan=self.plan)
        mock=patch("scripts.haa.protected_workflow.checked_bound_card",return_value=self.card)
        mock.start()
        self.addCleanup(mock.stop)

    def test_completion_not_plan_done(self):
        self.workflow.complete_task(("a.txt",))
        snap=self.plan.read_snapshot()
        self.assertEqual(snap.completed_tasks,("t",))
        self.assertEqual(snap.workflow_state,"ACTIVE")
        self.assertEqual(snap.validation_summary,{"status":"PENDING"})
        self.adapter.authority.close.assert_called_once()
        with self.assertRaises(ClosureError):
            self.workflow.complete_task(("a.txt",))

    def test_pending_plan_cannot_request_closure(self):
        requester=Mock()
        with self.assertRaises(ClosureError):
            self.workflow.request_close(requester)
        requester.request_approval.assert_not_called()

    def test_verified_commit_but_failed_record_stops(self):
        with patch.object(self.plan,"record_verified_task",side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.workflow.complete_task(("a.txt",))
        self.assertEqual(self.plan.read_snapshot().completed_tasks,())
        with self.assertRaisesRegex(ClosureError,"WORKFLOW_STOPPED"):
            self.workflow.complete_task(("a.txt",))
        self.adapter.commit.assert_called_once()

    def test_uncertain_record_blocks_new_workflow(self):
        with patch.object(self.plan,"record_verified_task",side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.workflow.complete_task(("a.txt",))
        second=ProtectedWorkflow(commit_adapter=self.adapter,plan=self.plan)
        with self.assertRaisesRegex(ClosureError,"TASK_ATTEMPT_BLOCKED"):
            second.complete_task(("a.txt",))
        self.adapter.commit.assert_called_once()

    def test_ready_requires_separate_exact_head_validation(self):
        self.workflow.complete_task(("a.txt",))
        with self.assertRaisesRegex(ClosureError,"PLAN_VALIDATION_FAILED"):
            self.workflow.mark_ready(validation=lambda head,s:{"status":"PASS","head":"wrong","evidenceDigest":"sha256:x"})
        ready=self.workflow.mark_ready(validation=lambda head,s:{"status":"PASS","head":head,
            "evidenceDigest":digest_json({"validation":"fixture"})})
        self.assertEqual(ready.workflow_state,"PLAN_READY_FOR_APPROVAL")
