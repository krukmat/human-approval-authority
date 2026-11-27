#!/usr/bin/env python3
"""Local read-only certification gate; never activates HAA or calls Touch ID."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(argv):
    return subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, check=False)


def git(*args):
    result = run(["git", *args])
    if result.returncode:
        raise RuntimeError("GIT_INSPECTION_FAILED")
    return result.stdout.strip()


def main():
    result = {"schema": "workflow.haa-candidate-gate.v1", "status": "BLOCKED",
              "runtime_enforcement": False, "physical_certification": False,
              "host_isolation": "NOT_TESTED", "verification_backend": "NOT_CERTIFIED",
              "activation": "NO_GO"}
    try:
        head = git("rev-parse", "HEAD")
        result["head"] = head
        if git("status", "--porcelain", "--untracked-files=normal"):
            raise RuntimeError("CANDIDATE_CHECKOUT_NOT_CLEAN")
        if sys.version_info < (3, 11):
            raise RuntimeError("PYTHON_3_11_REQUIRED")
        import cryptography
        result["python"] = sys.version.split()[0]
        result["cryptography"] = cryptography.__version__
        # Ensure the suite uses the very interpreter selected for this gate.
        env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
        tests = subprocess.run(["sh", "scripts/haa/run-tests.sh"], cwd=ROOT,
                               env=env, text=True, capture_output=True, check=False)
        result["test_exit_code"] = tests.returncode
        result["test_output"] = (tests.stdout + tests.stderr)[-24000:]
        # A successful unit suite is not deployment or physical evidence.
        # Keep the separate gates visible even when all candidate tests pass.
        if git("rev-parse", "HEAD") != head or git("status", "--porcelain", "--untracked-files=normal"):
            raise RuntimeError("CANDIDATE_CHANGED_DURING_GATE")
        result["status"] = "PASS_CANDIDATE_TESTS" if tests.returncode == 0 else "FAIL_CANDIDATE_TESTS"
    except Exception as exc:
        result["reason"] = str(exc)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS_CANDIDATE_TESTS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
