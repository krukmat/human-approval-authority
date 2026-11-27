from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.haa.authority import (
    HaaAuthorityError,
    authorize_exact_action,
    request_exact_action,
)
from scripts.haa.contracts import digest_json


class FakeRequester:
    def __init__(self, action):
        self.config = SimpleNamespace(executor_audience="executor")
        self.action = action

    def request_approval(self, action, ttl_ms):
        self.action = action
        return {
            "id": "req-1",
            "state": "PENDING",
            "actionDigest": digest_json(action),
            "intent": {"executorAudience": "executor"},
        }


class FakeExecutor:
    def __init__(self, action):
        self.config = SimpleNamespace(executor_audience="executor")
        self.action = action
        self.authorize_calls = []

    def get_request(self, request_id):
        return {
            "id": request_id,
            "state": "APPROVED",
            "actionDigest": digest_json(self.action),
            "intent": {"executorAudience": "executor"},
        }

    def authorize(self, **kwargs):
        self.authorize_calls.append(kwargs)
        return {
            "schema": "haa.execution-grant.v1",
            "requestId": kwargs["request_id"],
            "executionId": kwargs["execution_id"],
            "actionDigest": digest_json(self.action),
            "executorAudience": "executor",
            "issuedAt": "2026-11-03T12:00:00Z",
            "expiresAt": "2026-11-03T12:00:30Z",
            "authorityKeyId": "authority",
            "signatureAlgorithm": "Ed25519",
            "signature": "sig",
        }

    def authority_keys(self):
        return [{"keyId": "authority"}]


class AuthorityTest(unittest.TestCase):
    def setUp(self):
        self.action = {
            "schema": "haa.action.v1",
            "type": "demo.action.v1",
            "payload": {"resource": "r", "operation": "o"},
        }

    def test_request_exact_action_checks_returned_digest(self):
        result = request_exact_action(FakeRequester(self.action), self.action)
        self.assertEqual(result["state"], "PENDING")

    def test_mutated_action_is_denied_before_authorize(self):
        client = FakeExecutor(self.action)
        changed = {
            **self.action,
            "payload": {"resource": "r", "operation": "changed"},
        }
        with self.assertRaisesRegex(HaaAuthorityError, "ACTION_DIGEST_MISMATCH"):
            authorize_exact_action(
                client,
                request_id="req-1",
                execution_id="exec-1",
                actual_action=changed,
                actual_state={},
            )
        self.assertEqual(client.authorize_calls, [])

    def test_exact_action_requires_detached_verification(self):
        client = FakeExecutor(self.action)
        with mock.patch(
            "scripts.haa.authority.verify_execution_grant"
        ) as verify:
            grant = authorize_exact_action(
                client,
                request_id="req-1",
                execution_id="exec-1",
                actual_action=self.action,
                actual_state={"version": "v1"},
            )
        self.assertEqual(grant["executionId"], "exec-1")
        verify.assert_called_once()
        self.assertEqual(client.authorize_calls[0]["actual_state"], {"version": "v1"})


if __name__ == "__main__":
    unittest.main()
