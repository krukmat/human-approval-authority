#!/usr/bin/env python3
"""Side-effect-free HAA adapter CLI for Workflow W2."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from time import monotonic, sleep
from uuid import uuid4
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
    digest_json,
    build_plan_close_action,
    build_task_start_action,
    plan_close_actual_state,
    task_start_actual_state,
)

from scripts.haa.live_verify import _git
from scripts.haa.policy import PROJECT_SOURCES, pin_policy


class CheckpointBlocked(RuntimeError):
    """No permission to dispatch the prompt. No automatic retry."""


def _input_digest(path):
    path = Path(path)
    if not path.is_file():
        raise CheckpointBlocked("CHECKPOINT_INPUT_MISSING")
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if not raw or len(raw) > 1024 * 1024:
        raise CheckpointBlocked("INVALID_CHECKPOINT_INPUT")
    return sha256(raw).hexdigest()


def task_checkpoint(*, repository, repo_root, plan_id, task_id, rri,
                    task_card, prompt_file, allowed_paths, capabilities,
                    policy_files=(), wait_seconds=600, requester, executor,
                    on_pending=lambda request_id: None, clock=monotonic,
                    pause=sleep):
    """Existing workflow calls only when its policy requires HAA.

    Cooperative task-start gate, not a sandbox, lease, or general executor.
    Caller resolves RRI/HITL, checks readiness, selects the model and supplies
    the final card/prompt and exact scope. It must dispatch only the unchanged
    inputs immediately after success. No autonomous-task API call is needed.
    """
    if type(rri) is not int or rri < 0:
        raise CheckpointBlocked("INVALID_RRI")
    if type(wait_seconds) is not int or not 1 <= wait_seconds <= 600:
        raise CheckpointBlocked("INVALID_WAIT_SECONDS")
    if requester.config.executor_audience != executor.config.executor_audience:
        raise CheckpointBlocked("CHECKPOINT_AUDIENCE_MISMATCH")
    paths, caps = tuple(allowed_paths), tuple(capabilities)
    # Task start does not authorize publication or other privileged actions.
    if not caps or set(caps) - {"edit", "test", "review"}:
        raise CheckpointBlocked("SEPARATE_ACTION_REQUIRED")
    root = Path(repo_root).resolve()
    card = Path(task_card).absolute()
    prompt = Path(prompt_file).absolute()
    sources = tuple(sorted(set((*PROJECT_SOURCES.get(repository, ()), *policy_files))))
    if not sources:
        raise CheckpointBlocked("POLICY_SOURCE_REQUIRED")
    nonce = uuid4().hex

    def snapshot():
        if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise CheckpointBlocked("REPOSITORY_ROOT_MISMATCH")
        origin = _git(root, "remote", "get-url", "origin")
        if origin not in {f"https://github.com/{repository}", f"https://github.com/{repository}.git",
                          f"git@github.com:{repository}.git", f"ssh://git@github.com/{repository}.git"}:
            raise CheckpointBlocked("REPOSITORY_ORIGIN_MISMATCH")
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        head = _git(root, "rev-parse", "--verify", "HEAD")
        card_digest = _input_digest(card)
        prompt_digest = _input_digest(prompt)
        pin = pin_policy(root=root, repository=repository, card_sha256=card_digest,
                         rri=rri, requires_haa=True, capabilities=caps,
                         source_paths=sources, plan_close_requires_haa=False)
        # Bind the actual prompt and card to the existing signed sessionId.
        # No profile/schema migration; no credentials or prompt text in HAA.
        session = "checkpoint-" + nonce + "-" + sha256(
            (pin.digest() + ":" + prompt_digest).encode("ascii")).hexdigest()
        action = build_task_start_action(
            repository=repository, plan_id=plan_id, task_id=task_id,
            session_id=session, branch=branch, base_commit_sha=head,
            allowed_paths=paths, capabilities=caps, lease_ttl_seconds=60)
        return action, card_digest, prompt_digest

    expected = snapshot()
    action = expected[0]
    digest = digest_json(action)
    deadline = clock() + wait_seconds
    try:
        # Exactly one request. A lost response is ambiguous; never retry here.
        request = request_exact_action(requester, action, ttl_ms=wait_seconds * 1000)
        request_id = request.get("id")
        if not isinstance(request_id, str) or not request_id:
            raise CheckpointBlocked("INVALID_REQUEST_ID")
        on_pending(request_id)
        while True:
            if clock() >= deadline:
                raise CheckpointBlocked("WAIT_TIMED_OUT")
            current = requester.get_request(request_id)
            if (current.get("id") != request_id or current.get("actionDigest") != digest
                    or not isinstance(current.get("intent"), dict)
                    or current["intent"].get("executorAudience") != executor.config.executor_audience):
                raise CheckpointBlocked("REQUEST_BINDING_CHANGED")
            state = current.get("state")
            if state == "APPROVED":
                break
            if state not in {"REQUESTED", "PENDING"}:
                raise CheckpointBlocked("HAA_" + str(state))
            pause(min(1.0, max(0.0, deadline - clock())))
        # Reconstruct the action from the live task inputs, not from HAA.
        actual = snapshot()
        if actual != expected or clock() >= deadline:
            raise CheckpointBlocked("TASK_CHANGED_OR_EXPIRED")
        execution_id = uuid4().hex
        grant = authorize_exact_action(executor, request_id=request_id,
            execution_id=execution_id, actual_action=actual[0],
            actual_state=task_start_actual_state(actual[0]))
        if snapshot() != expected or clock() >= deadline:
            raise CheckpointBlocked("TASK_CHANGED_AFTER_CONSUMPTION")
        # Detached verification has already checked signature, TTL and audience.
        # Check freshness once more following the final input re-read.
        from datetime import UTC, datetime
        if datetime.fromisoformat(grant["expiresAt"].replace("Z", "+00:00")) <= datetime.now(UTC):
            raise CheckpointBlocked("GRANT_EXPIRED_BEFORE_DISPATCH")
        return {"status": "CHECKPOINT_PASS", "requestId": request_id,
                "executionId": execution_id, "actionDigest": digest,
                "cardSha256": expected[1], "promptSha256": expected[2],
                "expiresAt": grant["expiresAt"], "enforcement": "COOPERATIVE_ONLY"}
    except CheckpointBlocked:
        raise
    except Exception as exc:
        # Do not expose credentials or opaque upstream response contents.
        raise CheckpointBlocked("HAA_UNAVAILABLE_OR_AUTHORIZATION_UNCERTAIN") from exc


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
    checkpoint = sub.add_parser("checkpoint", help="Gate an existing required HITL task; never launches a model.")
    checkpoint.add_argument("--repository", required=True)
    checkpoint.add_argument("--repo-root", required=True)
    checkpoint.add_argument("--plan-id", required=True)
    checkpoint.add_argument("--task-id", required=True)
    checkpoint.add_argument("--rri", type=int, required=True)
    checkpoint.add_argument("--task-card", required=True)
    checkpoint.add_argument("--prompt-file", required=True)
    checkpoint.add_argument("--allow-path", action="append", required=True)
    checkpoint.add_argument("--capability", choices=["edit", "test", "review"], action="append", required=True)
    checkpoint.add_argument("--policy-file", action="append", default=[])
    checkpoint.add_argument("--wait-seconds", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "checkpoint":
        try:
            result = task_checkpoint(
                repository=args.repository, repo_root=args.repo_root, plan_id=args.plan_id,
                task_id=args.task_id, rri=args.rri, task_card=args.task_card,
                prompt_file=args.prompt_file, allowed_paths=args.allow_path,
                capabilities=args.capability, policy_files=args.policy_file,
                wait_seconds=args.wait_seconds,
                requester=HaaRequesterClient(RequesterConfig.from_env()),
                executor=HaaExecutorClient(ExecutorConfig.from_env()),
                on_pending=lambda request_id: print("HAA_REQUEST " + json.dumps(
                    {"requestId": request_id}), file=sys.stderr, flush=True))
            _write_json(result)
            return 0
        except CheckpointBlocked as exc:
            _write_json({"status": "BLOCKED", "reason": str(exc)})
            return 2
        except Exception:
            _write_json({"status": "BLOCKED", "reason": "INVALID_INPUT_OR_CONFIGURATION"})
            return 2

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
