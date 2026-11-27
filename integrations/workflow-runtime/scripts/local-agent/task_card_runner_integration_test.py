"""Retained upstream runner integration tests; NOT part of the portable parser gate.

Requires the actual repository-specific run_local_task and dependencies, staged
and pinned by the integration controller. Do not stub the missing runner.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task_card import LegacyTaskCardConversionRequired, parse_task_card
from task_card_test import _v2
import run_local_task as rlt


class TaskCardRunnerIntegrationTest(unittest.TestCase):
    def test_runner_executes_only_structured_argv_and_preserves_ids(self):
        card = parse_task_card(_v2())
        boundary = Mock()
        observed = {}

        def execute(argv, worktree_dir, active_boundary):
            observed["argv"] = argv
            return {"tool": "run_command", "argv": argv, "ok": True, "returncode": 0, "stdout": "", "stderr": ""}

        with patch.object(rlt.session_loop, "_run_command_with_timeout", side_effect=execute):
            result = rlt.build_default_test_runner(card, boundary)("/tmp/worktree")

        self.assertTrue(result["passed"])
        self.assertEqual(observed["argv"], ["env", "MODE=test", "cargo", "test"])
        self.assertEqual(result["commands"][0]["command_id"], "verify-unit")
        self.assertEqual(result["commands"][0]["criterion_ids"], ["HP-1"])

    def test_invalid_legacy_prose_fails_before_context_or_model(self):
        data = {"task_id": "old", "spec": "old", "allowed_paths": [], "acceptance_tests": ["Validation code uses typed input."]}
        chat = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "card.json")
            out = os.path.join(tmp, "out.json")
            with open(path, "w", encoding="utf-8") as handle:
                import json
                json.dump(data, handle)
            with self.assertRaises(LegacyTaskCardConversionRequired):
                rlt.main(["--card", path, "--legacy-card", "--worktree", tmp, "--out", out], chat_fn=chat)
        chat.assert_not_called()



if __name__ == "__main__":
    unittest.main()
