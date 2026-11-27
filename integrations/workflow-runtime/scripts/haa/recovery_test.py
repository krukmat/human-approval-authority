"""W3.T3.7 local recovery/failure tests; no live HAA/biometrics."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest

from scripts.haa.authority_lease import AuthorityLease, LeaseStore
from scripts.haa.recovery import (
    recover_all_attempts, recover_all_leases, recover_attempt,
)
from scripts.haa.request_checkpoint import (
    Checkpoint, CheckpointError, CheckpointStore, stop_waiting,
)


class FakeRequester:
    def __init__(self):
        self.status = "PENDING"
        self.calls = 0
        self.bad_digest = False
        self.unavailable = False

    def get_request(self, request_id):
        self.calls += 1
        if self.unavailable:
            raise TimeoutError("HAA unreachable")
        return {
            "id": request_id,
            "actionDigest": "sha256:bad" if self.bad_digest else "sha256:action",
            "intent": {"executorAudience": "executor-1"},
            "state": self.status,
        }


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.checkpoints = CheckpointStore(base / "checkpoints")
        self.leases = LeaseStore(base / "leases", signing_key=b"executor-secret-" * 3)
        self.requester = FakeRequester()
        self.now = datetime(2026, 11, 5, 14, tzinfo=UTC)

    def checkpoint(self, state="WAITING_FOR_HUMAN", *,
                   request_id="request-1", attempt_id="1"*32):
        return self.checkpoints.create(Checkpoint(
            attempt_id=attempt_id,
            execution_id="2"*32,
            action_digest="sha256:action",
            audience="executor-1",
            plan_id="haa-hitl-integration",
            task_id="W3.T3.7", session_id="session-1", rri=55,
            status=state, request_id=request_id,
        ))

    def lease(self, *, expires_in=600, lease_id="a"*32):
        return self.leases.create(AuthorityLease(
            lease_id=lease_id, request_id="request-1",
            execution_id="2"*32, action_digest="sha256:action",
            repository="example/workflow-fixture",
            plan_id="haa-hitl-integration", task_id="W3.T3.7",
            session_id="session-1", branch="feature/test",
            base_commit_sha="f"*40, scope_digest="sha256:scope",
            allowed_paths=("scripts/haa/**",),
            capabilities=("edit", "test"), rri=55,
            issued_at=self.now.isoformat(),
            expires_at=(self.now + timedelta(seconds=expires_in)).isoformat(),
        ))

    def test_hp_waiting_restart_uses_get_only_and_does_not_auto_approve(self):
        original = self.checkpoint()
        recovered = recover_attempt(self.requester, self.checkpoints, original.attempt_id)
        self.assertEqual((recovered.outcome, recovered.state),
                         ("WAITING_FOR_HUMAN", "WAITING_FOR_HUMAN"))
        self.assertEqual(self.requester.calls, 1)
        self.requester.status = "APPROVED"
        recovered = recover_attempt(self.requester, self.checkpoints, original.attempt_id)
        self.assertEqual(recovered.outcome, "HOLD_FOR_TRUSTED_EXECUTOR")
        self.assertEqual(self.checkpoints.load(original.attempt_id).execution_id,
                         original.execution_id)

    def test_ec_restart_prepared_never_reposts_even_if_remote_created_request(self):
        item = self.checkpoint("PREPARED", request_id=None)
        recovered = recover_attempt(self.requester, self.checkpoints, item.attempt_id)
        self.assertEqual((recovered.outcome, recovered.state),
                         ("OPERATOR_RECONCILIATION", "REQUEST_UNCERTAIN"))
        self.assertEqual(self.requester.calls, 0)
        self.assertEqual(recover_attempt(self.requester, self.checkpoints, item.attempt_id).state,
                         "REQUEST_UNCERTAIN")

    def test_ec_in_flight_consume_crash_becomes_terminal_unverified(self):
        item = self.checkpoint("CONSUMPTION_IN_FLIGHT")
        recovered = recover_attempt(self.requester, self.checkpoints, item.attempt_id)
        self.assertEqual((recovered.outcome, recovered.state),
                         ("OPERATOR_RECONCILIATION", "CONSUMED_UNVERIFIED"))
        self.assertEqual(self.requester.calls, 0)
        self.assertEqual(self.checkpoints.load(item.attempt_id).execution_id,
                         item.execution_id)
        with self.assertRaises(CheckpointError):
            self.checkpoints.transition(item.attempt_id, "CONSUMED_UNVERIFIED", "APPROVED_NOT_CONSUMED")

    def test_ec_cancel_timeout_revoke_remote_revoked_and_expired_are_terminal(self):
        for reason, expected in (
            ("USER_CANCELLED", "CANCELLED_LOCAL"),
            ("LOCAL_TIMEOUT", "WAIT_TIMED_OUT"),
        ):
            with self.subTest(reason=reason):
                item = self.checkpoint(attempt_id=("1" if reason == "USER_CANCELLED" else "3")*32)
                stopped = stop_waiting(self.checkpoints, item.attempt_id, reason=reason)
                self.assertEqual(stopped.status, expected)
                self.assertEqual(recover_attempt(
                    self.requester, self.checkpoints, item.attempt_id
                ).outcome, "BLOCKED")
                with self.assertRaises(CheckpointError):
                    stop_waiting(self.checkpoints, item.attempt_id, reason=reason)

        for status, expected in (("REVOKED", "REVOKED"), ("EXPIRED", "EXPIRED")):
            item = self.checkpoint(attempt_id=("4" if status == "REVOKED" else "5")*32)
            self.requester.status = status
            result = recover_attempt(self.requester, self.checkpoints, item.attempt_id)
            self.assertEqual((result.outcome, result.state), ("BLOCKED", expected))

    def test_ec_remote_timeout_or_digest_mismatch_does_not_advance_checkpoint(self):
        item = self.checkpoint()
        self.requester.unavailable = True
        result = recover_attempt(self.requester, self.checkpoints, item.attempt_id)
        self.assertEqual(result.outcome, "REMOTE_STATUS_UNAVAILABLE")
        self.assertEqual(self.checkpoints.load(item.attempt_id).status, "WAITING_FOR_HUMAN")
        self.requester.unavailable = False
        self.requester.bad_digest = True
        result = recover_attempt(self.requester, self.checkpoints, item.attempt_id)
        self.assertEqual(result.outcome, "REMOTE_STATUS_UNAVAILABLE")
        self.assertEqual(self.checkpoints.load(item.attempt_id).status, "WAITING_FOR_HUMAN")

    def test_ec_cancelled_attempt_revokes_matching_sealed_lease(self):
        item = self.checkpoint()
        self.lease()
        stop_waiting(self.checkpoints, item.attempt_id, reason="USER_CANCELLED")
        result = recover_attempt(
            self.requester, self.checkpoints, item.attempt_id, leases=self.leases,
        )
        self.assertEqual(result.outcome, "BLOCKED")
        self.assertEqual(self.leases.load("a"*32).status, "REVOKED")

    def test_hp_restart_active_lease_requires_live_guard_never_allow(self):
        self.lease()
        result = recover_all_leases(self.leases, now=self.now + timedelta(seconds=2))
        self.assertEqual(result[0].outcome, "NEEDS_LIVE_SCOPE_CHECK")
        self.assertNotEqual(result[0].outcome, "ALLOW")
        self.assertEqual(self.leases.load("a"*32).status, "ACTIVE")

    def test_ec_restart_expired_or_bad_hmac_blocks_and_revokes(self):
        self.lease(expires_in=60)
        expired = recover_all_leases(self.leases, now=self.now + timedelta(minutes=2))
        self.assertEqual(expired[0].outcome, "EXPIRED_REVOKED")
        self.assertEqual(self.leases.load("a"*32).status, "REVOKED")

        wrong = LeaseStore(self.leases.directory, signing_key=b"another-secret-" * 3)
        bad = recover_all_leases(wrong, now=self.now)
        self.assertEqual(bad[0].outcome, "BLOCKED")

    def test_ec_clock_rollback_revokes_future_lease(self):
        self.lease()
        result = recover_all_leases(self.leases, now=self.now - timedelta(seconds=1))
        self.assertEqual((result[0].outcome, result[0].state),
                         ("NOT_YET_VALID_REVOKED", "REVOKED"))

    def test_ec_mixed_recovery_never_issues_request_or_authority(self):
        self.checkpoint("PREPARED", request_id=None, attempt_id="1"*32)
        self.checkpoint("WAITING_FOR_HUMAN", attempt_id="3"*32)
        self.requester.status = "REQUESTED"
        result = recover_all_attempts(self.requester, self.checkpoints)
        self.assertEqual(len(result), 2)
        self.assertEqual([entry.outcome for entry in result],
                         ["OPERATOR_RECONCILIATION", "WAITING_FOR_HUMAN"])
        self.assertEqual(self.requester.calls, 1)


if __name__ == "__main__":
    unittest.main()
