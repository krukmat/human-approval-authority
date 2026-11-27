import json
from pathlib import Path
import unittest
from scripts.haa.contracts import build_task_start_action, digest_json

class WorkflowParityTest(unittest.TestCase):
    def test_cross_language_fixture(self):
        f=json.loads((Path(__file__).resolve().parents[2]/"fixtures/action-parity.json").read_text())
        s=f["scope"]
        action=build_task_start_action(repository=s["repository"],plan_id=s["planId"],
            task_id=s["taskId"],session_id=s["sessionId"],branch=s["branch"],
            base_commit_sha=s["baseCommitSha"],allowed_paths=s["allowedPaths"],
            capabilities=s["capabilities"],lease_ttl_seconds=f["leaseTtlSeconds"])
        self.assertEqual(action["payload"]["scopeDigest"],f["scopeDigest"])
        self.assertEqual(digest_json(action),f["actionDigest"])
