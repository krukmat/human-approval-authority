"""Local Git integration tests for W3.T3.6 scope/risk escalation guard."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from scripts.haa.authority_lease import AuthorityLease, LeaseStore
from scripts.haa.contracts import build_task_start_action
from scripts.haa.lease_guard import evaluate_lease_operation
from scripts.haa.live_verify import TrustedTask


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


class LeaseGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "repo"
        root.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "feature/test", str(root)], check=True
        )
        git(root, "config", "user.email", "test@example.invalid")
        git(root, "config", "user.name", "HAA lease test")
        git(root, "remote", "add", "origin", "https://github.com/example/workflow-fixture.git")
        (root / "README.md").write_text("base\n")
        git(root, "add", "README.md")
        git(root, "commit", "-qm", "baseline")
        self.root = root
        self.card = root / "task-card.json"
        self.card.write_text(json.dumps({
            "schema_version": 2,
            "card_id": "W3.T3.6",
            "task_id": "W3.T3.6",
            "spec": "Implement scope escalation guard",
            "allowed_paths": ["scripts/haa/**"],
            "acceptance_criteria": [], "verification_commands": [],
            "rri": 55, "band": "Med-high",
            "plan": "docs/plan/haa-hitl-integration.md",
        }))
        self.trusted = TrustedTask(
            repo_root=root, repository="example/workflow-fixture",
            card_path=self.card, session_id="session-1",
            capabilities=("edit", "test", "review", "commit"),
            lease_ttl_seconds=600,
        )
        head = git(root, "rev-parse", "HEAD")
        action = build_task_start_action(
            repository="example/workflow-fixture", plan_id="haa-hitl-integration",
            task_id="W3.T3.6", session_id="session-1",
            branch="feature/test", base_commit_sha=head,
            allowed_paths=["scripts/haa/**"],
            capabilities=["edit", "test", "review", "commit"],
            lease_ttl_seconds=600,
        )
        now = datetime(2026, 11, 5, 14, tzinfo=UTC)
        self.now = now
        self.store = LeaseStore(Path(self.temp.name) / "lease-state", signing_key=b"A" * 32)
        self.lease = self.store.create(AuthorityLease(
            lease_id="a" * 32, request_id="req-1", execution_id="b" * 32,
            action_digest="sha256:approved", repository="example/workflow-fixture",
            plan_id="haa-hitl-integration", task_id="W3.T3.6",
            session_id="session-1", branch="feature/test",
            base_commit_sha=head, scope_digest=action["payload"]["scopeDigest"],
            allowed_paths=("scripts/haa/**",),
            capabilities=("commit", "edit", "review", "test"),
            rri=55, issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=10)).isoformat(),
        ))

    def decide(self, operation="test", *, paths=(), task=None, now=None):
        return evaluate_lease_operation(
            store=self.store, lease_id=self.lease.lease_id,
            trusted_task=task or self.trusted, operation=operation,
            touched_paths=paths, now=now or self.now + timedelta(seconds=1),
        )

    def test_hp_same_scope_supports_repeated_ops_and_advanced_head(self):
        self.assertEqual(self.decide("test").outcome, "ALLOW")
        self.assertEqual(self.decide("review").outcome, "ALLOW")
        self.assertEqual(
            self.decide("edit", paths=("scripts/haa/module.py",)).outcome, "ALLOW"
        )
        (self.root / "scripts/haa").mkdir(parents=True)
        (self.root / "scripts/haa/module.py").write_text("ok\n")
        git(self.root, "add", "scripts/haa/module.py")
        git(self.root, "commit", "-qm", "allowed task commit")
        self.assertEqual(
            self.decide("commit", paths=("scripts/haa/module.py",)).outcome, "ALLOW"
        )
        self.assertEqual(self.store.load(self.lease.lease_id).status, "ACTIVE")

    def test_ec_plan_close_merge_never_use_task_lease(self):
        self.assertEqual(self.decide("plan_close").action_profile, "workflow.plan.close.v1")
        self.assertEqual(self.decide("merge").action_profile, "git.merge.v1")
        self.assertEqual(self.decide("push").outcome, "BLOCK")
        self.assertEqual(self.decide("deploy").outcome, "BLOCK")
        self.assertEqual(self.store.load(self.lease.lease_id).status, "ACTIVE")

    def test_ec_task_session_or_rri_drift_revokes(self):
        drift = replace(self.trusted, session_id="session-2")
        decision = self.decide(task=drift)
        self.assertEqual((decision.outcome, decision.reason),
                         ("REQUIRE_HAA", "TASK_OR_RRI_CHANGED"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_clock_before_issuance_revokes(self):
        decision = self.decide(now=self.now - timedelta(seconds=1))
        self.assertEqual((decision.outcome, decision.reason),
                         ("REQUIRE_HAA", "LEASE_NOT_YET_VALID"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_expiration_and_capability_escalation(self):
        expired = self.decide(now=self.now + timedelta(minutes=11))
        self.assertEqual((expired.outcome, expired.reason), ("REQUIRE_HAA", "LEASE_EXPIRED"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_path_scope_expansion_revokes(self):
        result = self.decide("edit", paths=("other/private.txt",))
        self.assertEqual((result.outcome, result.reason),
                         ("REQUIRE_HAA", "PATH_OUTSIDE_SCOPE"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_symlink_or_traversal_is_not_a_path_capability(self):
        self.assertEqual(self.decide("edit", paths=("../outside",)).outcome, "REQUIRE_HAA")
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_symlinked_parent_cannot_escape_approved_path_scope(self):
        safe = self.root / "scripts/haa"
        safe.mkdir(parents=True)
        other = self.root / "other"
        other.mkdir()
        (other / "private.txt").write_text("secret\\n")
        (safe / "shortcut").symlink_to(other, target_is_directory=True)
        result = self.decide("edit", paths=("scripts/haa/shortcut/private.txt",))
        self.assertEqual((result.outcome, result.reason),
                         ("REQUIRE_HAA", "PATH_OUTSIDE_SCOPE"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_modified_card_scope_or_rri_requires_reapproval(self):
        card = json.loads(self.card.read_text())
        card["rri"] = 70
        self.card.write_text(json.dumps(card))
        decision = self.decide()
        self.assertEqual((decision.outcome, decision.reason),
                         ("REQUIRE_HAA", "TASK_OR_RRI_CHANGED"))
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_branch_change_and_unrelated_history(self):
        git(self.root, "checkout", "-qb", "feature/other")
        self.assertEqual(self.decide().reason, "BRANCH_CHANGED")
        self.assertEqual(self.store.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_invalid_signing_key_blocks_even_for_same_repo(self):
        wrong = LeaseStore(self.store.directory, signing_key=b"B" * 32)
        result = evaluate_lease_operation(
            store=wrong, lease_id=self.lease.lease_id,
            trusted_task=self.trusted, operation="test", now=self.now,
        )
        self.assertEqual(result.outcome, "BLOCK")

    def test_ec_edit_or_commit_requires_actual_affected_paths(self):
        self.assertEqual(self.decide("edit").reason, "AFFECTED_PATHS_REQUIRED")
        self.assertEqual(self.decide("commit").reason, "AFFECTED_PATHS_REQUIRED")
        self.assertEqual(self.store.load(self.lease.lease_id).status, "ACTIVE")


if __name__ == "__main__":
    unittest.main()
