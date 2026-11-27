"""W3.T3.4 proof that HAA authorization binds live Git/card state."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.haa.contracts import digest_json
from scripts.haa.live_verify import (
    LiveAuthorityError, TrustedAuthorityPin, TrustedTask,
    live_task_action, verify_live_task_authorization,
)
from scripts.haa.request_checkpoint import Checkpoint, CheckpointError, CheckpointStore


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


class Executor:
    def __init__(self, digest: str, *, mutator=None):
        self.config = SimpleNamespace(executor_audience="executor-1")
        self.digest = digest
        self.state = "APPROVED"
        self.calls = 0
        self.mutator = mutator
        self.pem = "test-pinned-public-key"
        self.pin = TrustedAuthorityPin(
            "key-1", sha256(self.pem.encode()).hexdigest()
        )

    def get_request(self, request_id):
        return {"id": request_id, "actionDigest": self.digest,
                "intent": {"executorAudience": "executor-1"}, "state": self.state}

    def authority_keys(self):
        return [{"keyId": "key-1", "status": "ACTIVE",
                 "algorithm": "Ed25519", "publicKeyPem": self.pem}]

    def authorize(self, **kwargs):
        self.calls += 1
        if self.mutator is not None:
            self.mutator()
        return {"requestId": kwargs["request_id"],
                "executionId": kwargs["execution_id"],
                "actionDigest": self.digest, "authorityKeyId": "key-1"}


class LiveVerificationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "feature/test", str(root)], check=True)
        git(root, "config", "user.email", "test@example.invalid")
        git(root, "config", "user.name", "W3 Tests")
        git(root, "remote", "add", "origin", "https://github.com/krukmat/workflow.git")
        (root / "README.md").write_text("baseline\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(root, "commit", "-qm", "test baseline")
        self.root = root
        self.card = root / "task-card.json"
        self.card.write_text(json.dumps({
            "schema_version": 2,
            "card_id": "W3.T3.4",
            "task_id": "W3.T3.4",
            "spec": "Prepare live HAA task verification",
            "allowed_paths": ["scripts/haa/**"],
            "acceptance_criteria": [],
            "verification_commands": [],
            "rri": 55,
            "band": "Med-high",
            "plan": "docs/plan/haa-hitl-integration.md",
        }), encoding="utf-8")
        self.task = TrustedTask(
            repo_root=root, repository="example/workflow-fixture",
            card_path=self.card, session_id="session-1",
            capabilities=("edit", "test"), lease_ttl_seconds=300,
        )
        self.action, self.state, self.rri = live_task_action(self.task)
        self.store = CheckpointStore(Path(self.temp.name) / "private-haa")
        self.checkpoint = Checkpoint(
            attempt_id="1" * 32, execution_id="2" * 32,
            action_digest=digest_json(self.action),
            audience="executor-1", plan_id="haa-hitl-integration",
            task_id="W3.T3.4", session_id="session-1",
            rri=55, status="APPROVED_NOT_CONSUMED", request_id="req-1",
        )
        self.store.create(self.checkpoint)

    def test_hp_exact_live_state_verifies_without_execution_side_effect(self):
        executor = Executor(self.checkpoint.action_digest)
        with patch("scripts.haa.live_verify.verify_execution_grant") as verify:
            result = verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )
        self.assertEqual(result["status"], "VERIFIED_NO_SIDE_EFFECT")
        self.assertEqual(executor.calls, 1)
        verify.assert_called_once()
        self.assertEqual(self.store.load(self.checkpoint.attempt_id).status,
                         "VERIFIED_NO_SIDE_EFFECT")
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.state["currentHead"])

    def test_hp_durable_in_flight_marker_precedes_remote_consume(self):
        observed = []

        def inspect_during_authorize():
            observed.append(
                self.store.load(self.checkpoint.attempt_id).status
            )

        executor = Executor(self.checkpoint.action_digest, mutator=inspect_during_authorize)
        with patch("scripts.haa.live_verify.verify_execution_grant"):
            result = verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )
        self.assertEqual(observed, ["CONSUMPTION_IN_FLIGHT"])
        self.assertEqual(result["status"], "VERIFIED_NO_SIDE_EFFECT")

    def test_bound_session_pins_exact_card_and_rri(self):
        from scripts.haa.live_verify import bind_trusted_task, checked_bound_card
        task = bind_trusted_task(self.task, card_sha256=sha256(self.card.read_bytes()).hexdigest(),
                                 authoritative_rri=55)
        action, _, rri = live_task_action(task)
        self.assertEqual(action["payload"]["sessionId"], task.session_id)
        self.assertTrue(task.session_id.startswith("wfs1-"))
        self.assertEqual(rri, 55)
        self.assertEqual(checked_bound_card(task, self.root.resolve(), required=True).rri, 55)
        self.card.write_text(self.card.read_text() + " ")
        with self.assertRaisesRegex(LiveAuthorityError, "TASK_CARD_DIGEST_CHANGED"):
            live_task_action(task)

    def test_ec_symlinked_task_card_rejected_before_consumption(self):
        original = self.card.with_name("original.json")
        self.card.rename(original)
        self.card.symlink_to(original)
        executor = Executor(self.checkpoint.action_digest)
        with self.assertRaisesRegex(LiveAuthorityError, "INVALID_TASK_CARD"):
            verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )
        self.assertEqual(executor.calls, 0)

    def test_ec_git_head_drift_blocks_before_horizon_authorize(self):
        executor = Executor(self.checkpoint.action_digest)
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "move head")
        with self.assertRaisesRegex(LiveAuthorityError, "LIVE_TASK_ACTION_STALE"):
            verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )
        self.assertEqual(executor.calls, 0)

    def test_ec_bad_key_pin_or_pending_remote_denies(self):
        executor = Executor(self.checkpoint.action_digest)
        pin = TrustedAuthorityPin("key-1", "0" * 64)
        with self.assertRaisesRegex(LiveAuthorityError, "AUTHORITY_KEY_PIN_MISMATCH"):
            verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=pin,
            )
        self.assertEqual(executor.calls, 0)
        executor.state = "PENDING"
        with self.assertRaisesRegex(LiveAuthorityError, "REMOTE_APPROVAL_BINDING_MISMATCH"):
            verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )
        self.assertEqual(executor.calls, 0)

    def test_ec_post_consume_git_drift_keeps_authority_non_executable(self):
        def mutate():
            (self.root / "README.md").write_text("after consume\n", encoding="utf-8")
            git(self.root, "commit", "-qam", "head changed during consume")

        executor = Executor(self.checkpoint.action_digest, mutator=mutate)
        with patch("scripts.haa.live_verify.verify_execution_grant"):
            with self.assertRaisesRegex(LiveAuthorityError, "POST_CONSUMPTION_GIT_OR_CARD_DRIFT"):
                verify_live_task_authorization(
                    executor, self.store, self.checkpoint.attempt_id,
                    task=self.task, pin=executor.pin,
                )
        self.assertEqual(self.store.load(self.checkpoint.attempt_id).status,
                         "CONSUMED_UNVERIFIED")
        with self.assertRaises(CheckpointError):
            verify_live_task_authorization(
                executor, self.store, self.checkpoint.attempt_id,
                task=self.task, pin=executor.pin,
            )


if __name__ == "__main__":
    unittest.main()
