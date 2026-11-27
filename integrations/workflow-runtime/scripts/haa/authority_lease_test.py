"""Unit tests for W3.T3.5 internal, HMAC-sealed AuthorityLease."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.haa.authority_lease import (
    AuthorityLease, LeaseError, LeaseStore, activate_verified_task_lease,
)
from scripts.haa.contracts import build_task_start_action, digest_json
from scripts.haa.live_verify import TrustedAuthorityPin, TrustedTask
from scripts.haa.request_checkpoint import Checkpoint, CheckpointStore


class LeaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = LeaseStore(Path(self.temp.name) / "leases", signing_key=b"X" * 32)
        now = datetime(2026, 11, 5, 12, tzinfo=UTC)
        self.lease = AuthorityLease(
            lease_id="a" * 32,
            request_id="req-1",
            execution_id="b" * 32,
            action_digest="sha256:exact-action",
            repository="example/workflow-fixture",
            plan_id="haa-hitl-integration",
            task_id="W3.T3.5",
            session_id="session-1",
            branch="feature/test",
            base_commit_sha="c" * 40,
            scope_digest="sha256:scope",
            allowed_paths=("scripts/haa/**",),
            capabilities=("commit", "edit", "review", "test"),
            rri=55,
            issued_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=15)).isoformat(),
        )

    def test_hp_private_sealed_persistence_and_restart(self):
        self.storage.create(self.lease)
        reloaded = LeaseStore(self.storage.directory, signing_key=b"X" * 32)
        self.assertEqual(reloaded.load(self.lease.lease_id), self.lease)
        self.assertEqual(self.storage.directory.stat().st_mode & 0o077, 0)
        self.assertEqual(self.storage._file(self.lease.lease_id).stat().st_mode & 0o077, 0)
        with self.assertRaisesRegex(LeaseError, "LEASE_ALREADY_EXISTS"):
            self.storage.create(self.lease)

    def test_ec_authorization_cannot_issue_second_lease_even_after_revoke(self):
        self.storage.create(self.lease)
        self.storage.revoke(self.lease.lease_id)
        for second in (
            replace(self.lease, lease_id="d" * 32, execution_id="e" * 32),
            replace(self.lease, lease_id="d" * 32, request_id="req-2"),
        ):
            with self.assertRaisesRegex(LeaseError, "LEASE_AUTHORIZATION_ALREADY_USED"):
                self.storage.create(second)

    def test_ec_sealed_record_renamed_to_other_id_is_not_authority(self):
        self.storage.create(self.lease)
        self.storage._file(self.lease.lease_id).rename(self.storage._file("d" * 32))
        with self.assertRaisesRegex(LeaseError, "LEASE_ID_MISMATCH"):
            self.storage.load("d" * 32)

    def test_ec_tamper_or_wrong_executor_secret_blocks(self):
        self.storage.create(self.lease)
        with self.assertRaisesRegex(LeaseError, "LEASE_INTEGRITY_FAILED"):
            LeaseStore(self.storage.directory, signing_key=b"Y" * 32).load(self.lease.lease_id)
        path = self.storage._file(self.lease.lease_id)
        record = json.loads(path.read_text())
        record["capabilities"].append("deploy")
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(LeaseError, "LEASE_INTEGRITY_FAILED"):
            self.storage.load(self.lease.lease_id)

    def test_ec_explicit_revoke_is_durable_and_idempotent(self):
        self.storage.create(self.lease)
        self.assertEqual(self.storage.revoke(self.lease.lease_id).status, "REVOKED")
        self.assertEqual(self.storage.revoke(self.lease.lease_id).status, "REVOKED")
        self.assertEqual(self.storage.load(self.lease.lease_id).status, "REVOKED")

    def test_ec_unsafe_ttl_and_capabilities_fail_before_persistence(self):
        for replacement in (
            replace(self.lease, expires_at=(datetime.fromisoformat(self.lease.issued_at)
                                            + timedelta(minutes=31)).isoformat()),
            replace(self.lease, capabilities=("deploy",)),
            replace(self.lease, allowed_paths=("../escape",)),
            replace(self.lease, rri=-1),
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(LeaseError):
                    self.storage.create(replacement)
        with self.assertRaisesRegex(LeaseError, "LEASE_SIGNING_KEY_REQUIRED"):
            LeaseStore(self.storage.directory, signing_key=b"short")

    def test_hp_activation_calls_real_verifier_same_process_then_seals_lease(self):
        action = build_task_start_action(
            repository="example/workflow-fixture", plan_id="haa-hitl-integration",
            task_id="W3.T3.5", session_id="session-1",
            branch="feature/test", base_commit_sha="c" * 40,
            allowed_paths=["scripts/haa/**"],
            capabilities=["test", "edit"], lease_ttl_seconds=300,
        )
        action_digest = digest_json(action)
        checkpoints = CheckpointStore(Path(self.temp.name) / "checkpoints")
        approved = checkpoints.create(Checkpoint(
            attempt_id="1" * 32, execution_id="2" * 32,
            action_digest=action_digest, audience="executor-1",
            plan_id="haa-hitl-integration", task_id="W3.T3.5",
            session_id="session-1", rri=55,
            status="APPROVED_NOT_CONSUMED", request_id="req-1",
        ))
        task = TrustedTask(
            repo_root=Path(self.temp.name), repository="example/workflow-fixture",
            card_path=Path(self.temp.name) / "card.json", session_id="session-1",
            capabilities=("edit", "test"), lease_ttl_seconds=300,
        )
        pin = TrustedAuthorityPin("key-1", "a" * 64)
        called = []

        def fake_detached_verified(*_args, **kwargs):
            called.append(kwargs)
            checkpoints.transition(
                approved.attempt_id, "APPROVED_NOT_CONSUMED", "CONSUMPTION_IN_FLIGHT"
            )
            checkpoints.transition(
                approved.attempt_id, "CONSUMPTION_IN_FLIGHT", "VERIFIED_NO_SIDE_EFFECT"
            )
            return {"status": "VERIFIED_NO_SIDE_EFFECT", "grantDigest": digest_json({"fixture": "grant"})}

        with (
            patch("scripts.haa.authority_lease.verify_live_task_authorization", side_effect=fake_detached_verified),
            patch("scripts.haa.authority_lease.live_task_action", return_value=(action, {}, 55)),
        ):
            created = activate_verified_task_lease(
                executor=object(), checkpoints=checkpoints, leases=self.storage,
                attempt_id=approved.attempt_id, trusted_task=task,
                authority_pin=pin, now=datetime(2026, 11, 5, 12, tzinfo=UTC),
            )
        self.assertEqual(len(called), 1)
        self.assertEqual(created.scope_digest, action["payload"]["scopeDigest"])
        self.assertEqual(created.grant_digest, digest_json({"fixture": "grant"}))
        self.assertEqual(created.capabilities, ("edit", "test"))
        self.assertEqual(created.execution_id, approved.execution_id)
        self.assertEqual((datetime.fromisoformat(created.expires_at)
                          - datetime.fromisoformat(created.issued_at)).total_seconds(), 300)
        self.assertEqual(self.storage.load(created.lease_id), created)
        self.assertEqual(checkpoints.load(approved.attempt_id).status, "VERIFIED_NO_SIDE_EFFECT")


if __name__ == "__main__":
    unittest.main()
