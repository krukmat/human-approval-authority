from __future__ import annotations

import unittest

from scripts.haa.contracts import (
    HaaContractError,
    build_plan_close_action,
    build_plan_closure_manifest,
    build_task_start_action,
    digest_json,
    plan_close_actual_state,
    task_start_actual_state,
)


class ContractTest(unittest.TestCase):
    def test_hp_task_start_is_deterministic_and_normalized(self):
        kwargs = dict(
            repository="example/workflow-fixture",
            plan_id="haa-hitl-integration",
            task_id="W2.T2a",
            session_id="session-1",
            branch="feature/haa-hitl-w1-contract-policy",
            base_commit_sha="a" * 40,
            allowed_paths=["scripts/haa/**", "docs/**"],
            capabilities=["test", "edit", "commit", "review"],
            lease_ttl_seconds=1800,
        )
        first = build_task_start_action(**kwargs)
        second = build_task_start_action(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first["payload"]["allowedPaths"], ["docs/**", "scripts/haa/**"])
        self.assertEqual(first["payload"]["capabilities"], ["commit", "edit", "review", "test"])
        scope = {key: first["payload"][key] for key in (
            "repository", "planId", "taskId", "sessionId", "branch",
            "baseCommitSha", "allowedPaths", "capabilities",
        )}
        self.assertEqual(first["payload"]["scopeDigest"], digest_json(scope))
        self.assertEqual(task_start_actual_state(first)["currentHead"], "a" * 40)

    def test_ec_task_start_rejects_scope_escape_capability_and_bad_ttl(self):
        common = dict(
            repository="example/workflow-fixture",
            plan_id="p",
            task_id="t",
            session_id="s",
            branch="b",
            base_commit_sha="a" * 40,
            capabilities=["edit"],
        )
        with self.assertRaisesRegex(HaaContractError, "INVALID_ALLOWED_PATHS"):
            build_task_start_action(**common, allowed_paths=["../escape"])
        with self.assertRaisesRegex(HaaContractError, "INVALID_CAPABILITIES"):
            build_task_start_action(
                **{**common, "capabilities": ["deploy"]}, allowed_paths=["scripts/haa/**"]
            )
        with self.assertRaisesRegex(HaaContractError, "INVALID_LEASE_TTL"):
            build_task_start_action(
                **common, allowed_paths=["scripts/haa/**"], lease_ttl_seconds=1801
            )

    def test_hp_plan_close_binds_full_manifest_and_evidence(self):
        manifest = build_plan_closure_manifest(
            repository="example/workflow-fixture",
            plan_id="haa-hitl-integration",
            plan_version="1",
            branch="feature/haa-hitl-w1-contract-policy",
            final_commit_sha="b" * 40,
            required_tasks=["T2", "T1"],
            completed_tasks=["T1", "T2"],
            accepted_exceptions=["physical-smoke-pending"],
            unresolved_non_blockers=[],
            validation_summary={"status": "PASS", "checks": ["unit"]},
            evidence=["evidence-b", "evidence-a"],
        )
        action = build_plan_close_action(manifest)
        self.assertEqual(action["payload"]["requiredTaskCount"], 2)
        self.assertEqual(action["payload"]["completedTaskCount"], 2)
        self.assertEqual(action["payload"]["acceptedExceptionCount"], 1)
        self.assertEqual(action["payload"]["closureManifestDigest"], digest_json(manifest))
        self.assertEqual(plan_close_actual_state(action)["workflowState"], "PLAN_READY_FOR_APPROVAL")

    def test_ec_plan_close_rejects_incomplete_or_failed_validation(self):
        with self.assertRaisesRegex(HaaContractError, "REQUIRED_TASKS_NOT_COMPLETED"):
            build_plan_closure_manifest(
                repository="r",
                plan_id="p",
                plan_version="1",
                branch="b",
                final_commit_sha="c",
                required_tasks=["T1"],
                completed_tasks=[],
                accepted_exceptions=[],
                unresolved_non_blockers=[],
                validation_summary={"status": "PASS"},
                evidence=[],
            )
        with self.assertRaisesRegex(HaaContractError, "INVALID_VALIDATION_SUMMARY"):
            build_plan_closure_manifest(
                repository="r",
                plan_id="p",
                plan_version="1",
                branch="b",
                final_commit_sha="c",
                required_tasks=[],
                completed_tasks=[],
                accepted_exceptions=[],
                unresolved_non_blockers=[],
                validation_summary={"status": "FAIL"},
                evidence=[],
            )


if __name__ == "__main__":
    unittest.main()
