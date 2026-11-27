from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.haa import plan_closure_test
from scripts.haa.plan_closure import ClosureError
from scripts.haa.protected_plan import ProtectedPlanJournal


class ProtectedPlanTest(plan_closure_test.ClosureTest):
    """Reuse candidate fixtures; replace source and journal with canonical state."""
    def setUp(self):
        super().setUp()
        directory=Path(self.tmp.name).resolve()/"canonical"
        directory.mkdir(mode=0o700)
        self.journal=ProtectedPlanJournal.initialize(
            directory, signing_key=b"K"*32, repository="example/workflow-fixture",
            snapshot=self.snapshot)
        self.source=self.journal.source(self.source.repo_root,"example/workflow-fixture","p")

    # Candidate tests mutate their fixture callback; this source intentionally
    # cannot be mutated once request intent is persisted.
    def test_manifest_change_blocks_before_consume(self):
        from dataclasses import replace
        self.request()
        with self.assertRaisesRegex(ClosureError,"CANONICAL_PLAN_UPDATE_BLOCKED"):
            self.journal.update_snapshot(replace(self.snapshot,evidence=("different",)))
        self.executor.authorize.assert_not_called()

    def test_post_consume_drift_blocks_terminally(self):
        def drift(**_):
            (self.source.repo_root/"README.md").write_text("dirty")
            return {"fixture":"grant"}
        self.request()
        self.executor.authorize.side_effect=drift
        with patch("scripts.haa.plan_closure.verify_execution_grant"):
            with self.assertRaisesRegex(ClosureError,"CLOSURE_WORKTREE_NOT_CLEAN"):
                self.finish()
        self.assertEqual(self.journal.load()["state"],"CONSUMED_UNVERIFIED")
        self.assertEqual(self.journal.read_snapshot().workflow_state,"PLAN_READY_FOR_APPROVAL")

    def test_canonical_done_is_atomic_and_restart_readable(self):
        self.request()
        with patch("scripts.haa.plan_closure.verify_execution_grant"):
            self.finish()
        restored=ProtectedPlanJournal(self.journal.directory, signing_key=b"K"*32,
                                       repository="example/workflow-fixture",plan_id="p")
        self.assertEqual(restored.load()["state"],"PLAN_DONE")
        self.assertEqual(restored.read_snapshot().workflow_state,"PLAN_DONE")

    def test_pending_keeps_canonical_state(self):
        self.request()
        self.executor.get_request.return_value["state"]="PENDING"
        with self.assertRaises(ClosureError):
            self.finish()
        self.assertEqual(self.journal.read_snapshot().workflow_state,"PLAN_READY_FOR_APPROVAL")
