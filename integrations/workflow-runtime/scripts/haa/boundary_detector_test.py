"""Behavioral unit evidence for W3.T3.2's pure authority-boundary classifier."""

from __future__ import annotations

from dataclasses import replace
import unittest

from scripts.haa.boundary_detector import TaskScope, evaluate_authority_boundary


class AuthorityBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.low = TaskScope(
            repository="example/workflow-fixture",
            plan_id="haa-hitl-integration",
            task_id="W3.T3.2",
            session_id="session-1",
            branch="feature/haa-hitl-w3-boundary-detector",
            base_commit_sha="a" * 40,
            allowed_paths=("docs/**", "scripts/haa/**"),
            capabilities=("edit", "test", "review", "commit"),
            rri=25,
        )

    def test_hp_low_band_routine_actions_need_no_new_haa_prompt(self) -> None:
        for operation in ("task_start", "edit", "test", "review", "commit"):
            with self.subTest(operation=operation):
                decision = evaluate_authority_boundary(operation=operation, current_scope=self.low)
                self.assertEqual((decision.outcome, decision.action_profile), ("ALLOW", None))

    def test_hp_moderate_task_requires_exact_task_start_haa_profile(self) -> None:
        for operation in ("task_start", "edit", "test", "review"):
            with self.subTest(operation=operation):
                decision = evaluate_authority_boundary(
                    operation=operation, current_scope=replace(self.low, rri=26)
                )
                self.assertEqual(decision.outcome, "REQUIRE_HAA")
                self.assertEqual(decision.action_profile, "workflow.task.start.v1")

    def test_hp_plan_close_always_haa_even_for_low_band(self) -> None:
        decision = evaluate_authority_boundary(operation="plan_close", current_scope=self.low)
        self.assertEqual(decision.outcome, "REQUIRE_HAA")
        self.assertEqual(decision.action_profile, "workflow.plan.close.v1")

    def test_hp_git_merge_uses_existing_exact_profile(self) -> None:
        decision = evaluate_authority_boundary(operation="merge", current_scope=self.low)
        self.assertEqual(decision.outcome, "REQUIRE_HAA")
        self.assertEqual(decision.action_profile, "git.merge.v1")

    def test_ec_scope_session_branch_risk_drift_requires_new_authority(self) -> None:
        modifications = (
            {"session_id": "session-2"},
            {"branch": "main"},
            {"repository": "krukmat/other"},
            {"plan_id": "other-plan"},
            {"task_id": "other-task"},
            {"allowed_paths": ("scripts/haa/**",)},
            {"capabilities": ("edit", "test")},
            {"rri": 26},
            {"base_commit_sha": "b" * 40},
        )
        for change in modifications:
            with self.subTest(change=change):
                decision = evaluate_authority_boundary(
                    operation="test",
                    current_scope=replace(self.low, **change),
                    approved_scope=self.low,
                )
                self.assertEqual(decision.outcome, "REQUIRE_HAA")
                self.assertEqual(decision.reason, "SCOPE_OR_RISK_CHANGED")

    def test_ec_unchanged_snapshot_never_waives_high_rri_gate(self) -> None:
        high = replace(self.low, rri=55)
        decision = evaluate_authority_boundary(
            operation="edit", current_scope=high, approved_scope=high
        )
        self.assertEqual(decision.outcome, "REQUIRE_HAA")

    def test_ec_block_out_of_scope_or_unsupported_sensitive_actions(self) -> None:
        decision = evaluate_authority_boundary(
            operation="commit", current_scope=replace(self.low, capabilities=("edit", "test"))
        )
        self.assertEqual((decision.outcome, decision.reason), ("BLOCK", "CAPABILITY_OUT_OF_SCOPE"))
        for operation in (
            "push", "create_pr", "deploy", "release", "secrets", "delete",
            "overwrite", "migration", "external_call", "privileged_operation", "shell_anything",
        ):
            with self.subTest(operation=operation):
                self.assertEqual(
                    evaluate_authority_boundary(operation=operation, current_scope=self.low).outcome,
                    "BLOCK",
                )

    def test_ec_fail_closed_invalid_rri_paths_or_missing_scope(self) -> None:
        for scope in (
            replace(self.low, rri=-1),
            replace(self.low, rri=True),
            replace(self.low, allowed_paths=("../escape",)),
            replace(self.low, capabilities=("deploy",)),
            replace(self.low, session_id=""),
            None,
        ):
            with self.subTest(scope=scope):
                decision = evaluate_authority_boundary(operation="test", current_scope=scope)
                self.assertEqual(decision.outcome, "BLOCK")

    def test_ec_unknown_or_blank_operation_blocks(self) -> None:
        for operation in ("", "other", None, 9):
            with self.subTest(operation=operation):
                self.assertEqual(
                    evaluate_authority_boundary(operation=operation, current_scope=self.low).outcome,
                    "BLOCK",
                )


if __name__ == "__main__":
    unittest.main()
