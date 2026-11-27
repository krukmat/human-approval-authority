"""Candidate W4 tests; synthetic journal, fake network, no real plan closure."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.haa.contracts import digest_json
from scripts.haa.live_verify import TrustedAuthorityPin
from scripts.haa.plan_closure import (
    ClosureError, ClosureJournal, ClosureSource, PlanSnapshot,
    request_plan_close, finalize_plan_close,
)


class ClosureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "repo"
        root.mkdir()
        def git(*args):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        git("init", "-b", "test")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.invalid")
        git("remote", "add", "origin", "https://github.com/example/workflow-fixture.git")
        (root / "README.md").write_text("base")
        git("add", "README.md")
        git("commit", "-m", "base")
        self.snapshot = PlanSnapshot("PLAN_READY_FOR_APPROVAL", "p", "v1", ("t",), ("t",),
                                     (), (), {"status": "PASS"}, ("sha256:evidence",))
        self.source = ClosureSource(root, "example/workflow-fixture", "p", lambda: self.snapshot)
        self.journal = ClosureJournal(Path(self.tmp.name) / "journal", signing_key=b"K"*32,
                                      repository="example/workflow-fixture", plan_id="p")
        self.requester = Mock()
        self.requester.config = SimpleNamespace(executor_audience="exec")
        self.requester.request_approval.side_effect = lambda action, **_: {
            "id": "r", "actionDigest": digest_json(action), "intent": {"executorAudience": "exec"}}
        self.executor = Mock()
        self.executor.config = self.requester.config
        self.executor.authority_keys.return_value = [{"keyId": "k", "status": "ACTIVE",
                                                       "publicKeyPem": "fixture"}]
        self.pin = TrustedAuthorityPin("k", sha256(b"fixture").hexdigest())
        self.executor.authorize.return_value = {"fixture": "verified-grant"}

    def request(self):
        result = request_plan_close(source=self.source, journal=self.journal, requester=self.requester)
        self.executor.get_request.return_value = {
            "id": "r", "state": "APPROVED", "actionDigest": result["actionDigest"],
            "intent": {"executorAudience": "exec"},
        }
        return result

    def finish(self):
        return finalize_plan_close(source=self.source, journal=self.journal,
                                   executor=self.executor, pin=self.pin)

    def test_exact_candidate_close_and_no_replay(self):
        result = self.request()
        def check_in_flight(**_):
            self.assertEqual(self.journal.load()["state"], "CONSUMPTION_IN_FLIGHT")
            return {"fixture": "verified-grant"}
        self.executor.authorize.side_effect = check_in_flight
        with patch("scripts.haa.plan_closure.verify_execution_grant") as verify:
            done = self.finish()
        self.assertEqual(done["state"], "PLAN_DONE")
        self.assertEqual(done["executionId"], result["executionId"])
        self.assertEqual(done["grantDigest"], digest_json({"fixture": "verified-grant"}))
        verify.assert_called_once()
        with self.assertRaisesRegex(ClosureError, "CLOSURE_NOT_WAITING"):
            self.finish()
        self.executor.authorize.assert_called_once()

    def test_pending_never_consumes(self):
        self.request()
        self.executor.get_request.return_value["state"] = "PENDING"
        with self.assertRaisesRegex(ClosureError, "WAITING_FOR_HUMAN"):
            self.finish()
        self.executor.authorize.assert_not_called()

    def test_manifest_change_blocks_before_consume(self):
        self.request()
        self.snapshot = replace(self.snapshot, evidence=("different",))
        with self.assertRaisesRegex(ClosureError, "STALE_CLOSURE_APPROVAL"):
            self.finish()
        self.executor.authorize.assert_not_called()

    def test_post_consume_drift_blocks_terminally(self):
        self.request()
        def drift(**_):
            self.snapshot = replace(self.snapshot, evidence=("different",))
            return {"fixture": "grant"}
        self.executor.authorize.side_effect = drift
        with patch("scripts.haa.plan_closure.verify_execution_grant"):
            with self.assertRaisesRegex(ClosureError, "POST_CONSUMPTION_CLOSURE_DRIFT"):
                self.finish()
        self.assertEqual(self.journal.load()["state"], "CONSUMED_UNVERIFIED")
        with self.assertRaisesRegex(ClosureError, "CLOSURE_NOT_WAITING"):
            self.finish()

    def test_request_timeout_never_reposts(self):
        self.requester.request_approval.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.request()
        self.assertEqual(self.journal.load()["state"], "REQUEST_UNCERTAIN")
        with self.assertRaisesRegex(ClosureError, "CLOSURE_ATTEMPT_ALREADY_EXISTS"):
            self.request()
        self.requester.request_approval.assert_called_once()

    def test_dirty_worktree_never_creates_closure_request(self):
        (self.source.repo_root / "README.md").write_text("uncommitted")
        with self.assertRaisesRegex(ClosureError, "CLOSURE_WORKTREE_NOT_CLEAN"):
            self.request()
        self.requester.request_approval.assert_not_called()

    def test_signature_failure_never_marks_done(self):
        self.request()
        with patch("scripts.haa.plan_closure.verify_execution_grant", side_effect=ValueError("signature")):
            with self.assertRaises(ValueError):
                self.finish()
        self.assertEqual(self.journal.load()["state"], "CONSUMED_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
