from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from scripts.haa.client import (
    ExecutorConfig,
    HaaExecutorClient,
    HaaRequesterClient,
    RequesterConfig,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RecordingOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(self.responses.pop(0))


class ClientTest(unittest.TestCase):
    def test_requester_config_never_loads_executor_secret(self):
        env = {
            "HAA_BASE_URL": "http://haa",
            "HAA_REQUESTER_API_KEY": "requester-only",
            "HAA_APPROVER_PRINCIPAL_ID": "human",
            "HAA_EXECUTOR_AUDIENCE": "executor",
            "HAA_EXECUTOR_API_KEY": "must-not-be-read",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = RequesterConfig.from_env()
        self.assertEqual(config.api_key, "requester-only")
        self.assertFalse(hasattr(config, "executor_api_key"))

    def test_executor_config_never_loads_requester_secret(self):
        env = {
            "HAA_BASE_URL": "http://haa",
            "HAA_EXECUTOR_API_KEY": "executor-only",
            "HAA_EXECUTOR_AUDIENCE": "executor",
            "HAA_REQUESTER_API_KEY": "must-not-be-read",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = ExecutorConfig.from_env()
        self.assertEqual(config.api_key, "executor-only")
        self.assertFalse(hasattr(config, "requester_api_key"))

    def test_requester_creates_only_request_and_status_calls(self):
        opener = RecordingOpener([
            {"id": "req-1", "state": "PENDING"},
            {"id": "req-1", "state": "APPROVED"},
        ])
        client = HaaRequesterClient(
            RequesterConfig("http://haa", "requester", "human", "executor"),
            opener=opener,
        )
        action = {"schema": "haa.action.v1", "type": "demo.action.v1", "payload": {}}
        self.assertEqual(client.request_approval(action)["id"], "req-1")
        self.assertEqual(client.get_request("req-1")["state"], "APPROVED")
        first = opener.requests[0][0]
        self.assertEqual(first.get_method(), "POST")
        self.assertNotIn("/authorize", first.full_url)
        self.assertEqual(json.loads(first.data)["executorAudience"], "executor")

    def test_executor_authorize_and_key_calls_are_separate(self):
        opener = RecordingOpener([
            {"schema": "haa.execution-grant.v1"},
            [{"keyId": "authority"}],
        ])
        client = HaaExecutorClient(
            ExecutorConfig("http://haa", "executor-secret", "executor"),
            opener=opener,
        )
        grant = client.authorize(
            request_id="req-1",
            execution_id="exec-1",
            actual_action={"schema": "haa.action.v1"},
            actual_state={"version": "v1"},
        )
        self.assertEqual(grant["schema"], "haa.execution-grant.v1")
        self.assertEqual(client.authority_keys()[0]["keyId"], "authority")
        self.assertTrue(opener.requests[0][0].full_url.endswith("/authorize"))


if __name__ == "__main__":
    unittest.main()
