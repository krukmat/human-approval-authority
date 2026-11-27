from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("adapter.py").resolve()


class AdapterCliTest(unittest.TestCase):
    def test_direct_script_builds_task_start_from_arbitrary_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "build-task-start", "--repository", "example/workflow-fixture",
                    "--plan-id", "haa-hitl-integration",
                    "--task-id", "W2.T2e",
                    "--session-id", "session-1",
                    "--branch", "feature/haa-hitl-w1-contract-policy",
                    "--base-commit", "a" * 40,
                    "--allow-path", "scripts/haa/**",
                    "--capability", "test",
                ],
                cwd=directory,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        action = json.loads(result.stdout)
        self.assertEqual(action["type"], "workflow.task.start.v1")
        self.assertEqual(action["payload"]["capabilities"], ["test"])

    def test_invalid_scope_fails_without_network(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "build-task-start", "--repository", "example/workflow-fixture",
                "--plan-id", "p",
                "--task-id", "t",
                "--session-id", "s",
                "--branch", "b",
                "--base-commit", "a" * 40,
                "--allow-path", "../escape",
                "--capability", "test",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("INVALID_ALLOWED_PATHS", result.stderr)


if __name__ == "__main__":
    unittest.main()
