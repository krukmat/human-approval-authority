#!/usr/bin/env python3
"""Side-effect-free HAA adapter CLI for Workflow W2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.haa.authority import authorize_exact_action, request_exact_action
from scripts.haa.client import (
    ExecutorConfig,
    HaaExecutorClient,
    HaaRequesterClient,
    RequesterConfig,
)
from scripts.haa.contracts import (
    build_plan_close_action,
    build_task_start_action,
    plan_close_actual_state,
    task_start_actual_state,
)


def _json_file(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"INVALID_JSON_FILE:{path}") from exc


def _object_file(path: str) -> dict[str, Any]:
    value = _json_file(path)
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflow-haa",
        description=(
            "Build/request/authorize exact HAA actions. W2 is authority-only: "
            "this tool never mutates Workflow workflow state or creates leases."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    task = sub.add_parser("build-task-start")
    task.add_argument("--repository", required=True)
    task.add_argument("--plan-id", required=True)
    task.add_argument("--task-id", required=True)
    task.add_argument("--session-id", required=True)
    task.add_argument("--branch", required=True)
    task.add_argument("--base-commit", required=True)
    task.add_argument("--allow-path", action="append", required=True)
    task.add_argument(
        "--capability",
        action="append",
        choices=["edit", "test", "review", "commit"],
        required=True,
    )
    task.add_argument("--lease-ttl-seconds", type=int, default=1800)

    close = sub.add_parser("build-plan-close")
    close.add_argument("manifest_file")

    request = sub.add_parser("request")
    request.add_argument("action_file")
    request.add_argument("--ttl-ms", type=int, default=10 * 60_000)

    status = sub.add_parser("status")
    status.add_argument("request_id")

    authorize = sub.add_parser("authorize-and-verify")
    authorize.add_argument("request_id")
    authorize.add_argument("execution_id")
    authorize.add_argument("action_file")
    authorize.add_argument(
        "--actual-state-file",
        help=(
            "Explicit actual-state JSON. When omitted, the exact state is derived "
            "from a Workflow task-start/plan-close action for W2 smoke only."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "build-task-start":
        _write_json(
            build_task_start_action(
                repository=args.repository,
                plan_id=args.plan_id,
                task_id=args.task_id,
                session_id=args.session_id,
                branch=args.branch,
                base_commit_sha=args.base_commit,
                allowed_paths=args.allow_path,
                capabilities=args.capability,
                lease_ttl_seconds=args.lease_ttl_seconds,
            )
        )
        return 0

    if args.command == "build-plan-close":
        _write_json(build_plan_close_action(_object_file(args.manifest_file)))
        return 0

    if args.command == "request":
        client = HaaRequesterClient(RequesterConfig.from_env())
        result = request_exact_action(
            client,
            _object_file(args.action_file),
            ttl_ms=args.ttl_ms,
        )
        _write_json(
            {
                "requestId": result["id"],
                "state": result.get("state"),
                "actionDigest": result.get("actionDigest"),
            }
        )
        return 0

    if args.command == "status":
        client = HaaRequesterClient(RequesterConfig.from_env())
        result = client.get_request(args.request_id)
        _write_json(
            {
                "requestId": result["id"],
                "state": result.get("state"),
                "actionDigest": result.get("actionDigest"),
            }
        )
        return 0

    if args.command == "authorize-and-verify":
        action = _object_file(args.action_file)
        if args.actual_state_file:
            actual_state = _object_file(args.actual_state_file)
        elif action.get("type") == "workflow.task.start.v1":
            actual_state = task_start_actual_state(action)
        elif action.get("type") == "workflow.plan.close.v1":
            actual_state = plan_close_actual_state(action)
        else:
            raise ValueError("ACTUAL_STATE_REQUIRED_FOR_ACTION_PROFILE")

        client = HaaExecutorClient(ExecutorConfig.from_env())
        grant = authorize_exact_action(
            client,
            request_id=args.request_id,
            execution_id=args.execution_id,
            actual_action=action,
            actual_state=actual_state,
        )
        _write_json(
            {
                "status": "VERIFIED",
                "requestId": grant["requestId"],
                "executionId": grant["executionId"],
                "actionDigest": grant["actionDigest"],
                "executorAudience": grant["executorAudience"],
                "expiresAt": grant["expiresAt"],
                "authorityKeyId": grant["authorityKeyId"],
            }
        )
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"HAA_ADAPTER_ERROR:{exc}", file=sys.stderr)
        raise SystemExit(2)
