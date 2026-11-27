"""Pure Workflow↔HAA action contracts.

No network, credentials, HAA state, or workflow mutation belongs in this module.
All digests intentionally match HAA protocol-v1 canonical JSON semantics for the
value types used by the Workflow profiles.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Iterable

TASK_CAPABILITIES = frozenset({"edit", "test", "review", "commit"})
MIN_LEASE_TTL_SECONDS = 60
MAX_LEASE_TTL_SECONDS = 1800


class HaaContractError(ValueError):
    """The proposed authority object is unsafe or non-canonical."""


def canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise HaaContractError("INVALID_CANONICAL_INTEGER")
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(canonicalize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise HaaContractError("INVALID_CANONICAL_KEY")
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{canonicalize(value[key])}"
            for key in sorted(value, key=lambda k: k.encode('utf-16-be'))
        ) + "}"
    raise HaaContractError("INVALID_CANONICAL_VALUE")


def digest_json(value: Any) -> str:
    raw = hashlib.sha256(canonicalize(value).encode("utf-8")).digest()
    return "sha256:" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise HaaContractError(f"INVALID_{label}")
    return value


def _normalized_paths(values: Iterable[str]) -> list[str]:
    result = list(values)
    if not result:
        raise HaaContractError("INVALID_ALLOWED_PATHS")
    for path in result:
        if (
            not isinstance(path, str)
            or not path
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in path)
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise HaaContractError("INVALID_ALLOWED_PATHS")
    if len(set(result)) != len(result):
        raise HaaContractError("DUPLICATE_ALLOWED_PATH")
    return sorted(result, key=lambda k: k.encode('utf-16-be'))


def _normalized_capabilities(values: Iterable[str]) -> list[str]:
    result = list(values)
    if not result or any(value not in TASK_CAPABILITIES for value in result):
        raise HaaContractError("INVALID_CAPABILITIES")
    if len(set(result)) != len(result):
        raise HaaContractError("DUPLICATE_CAPABILITY")
    return sorted(result)


def build_task_scope(
    *,
    repository: str,
    plan_id: str,
    task_id: str,
    session_id: str,
    branch: str,
    base_commit_sha: str,
    allowed_paths: Iterable[str],
    capabilities: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(base_commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_commit_sha):
        raise HaaContractError("INVALID_BASE_COMMIT_SHA")
    scope = {
        "repository": _required_string(repository, "REPOSITORY"),
        "planId": _required_string(plan_id, "PLAN_ID"),
        "taskId": _required_string(task_id, "TASK_ID"),
        "sessionId": _required_string(session_id, "SESSION_ID"),
        "branch": _required_string(branch, "BRANCH"),
        "baseCommitSha": _required_string(base_commit_sha, "BASE_COMMIT_SHA"),
        "allowedPaths": _normalized_paths(allowed_paths),
        "capabilities": _normalized_capabilities(capabilities),
    }
    return scope


def build_task_start_action(
    *,
    repository: str,
    plan_id: str,
    task_id: str,
    session_id: str,
    branch: str,
    base_commit_sha: str,
    allowed_paths: Iterable[str],
    capabilities: Iterable[str],
    lease_ttl_seconds: int = MAX_LEASE_TTL_SECONDS,
) -> dict[str, Any]:
    if (
        isinstance(lease_ttl_seconds, bool)
        or not isinstance(lease_ttl_seconds, int)
        or not MIN_LEASE_TTL_SECONDS <= lease_ttl_seconds <= MAX_LEASE_TTL_SECONDS
    ):
        raise HaaContractError("INVALID_LEASE_TTL_SECONDS")
    scope = build_task_scope(
        repository=repository,
        plan_id=plan_id,
        task_id=task_id,
        session_id=session_id,
        branch=branch,
        base_commit_sha=base_commit_sha,
        allowed_paths=allowed_paths,
        capabilities=capabilities,
    )
    return {
        "schema": "haa.action.v1",
        "type": "workflow.task.start.v1",
        "payload": {
            **scope,
            "scopeDigest": digest_json(scope),
            "leaseTtlSeconds": lease_ttl_seconds,
        },
    }


def build_plan_closure_manifest(
    *,
    repository: str,
    plan_id: str,
    plan_version: str,
    branch: str,
    final_commit_sha: str,
    required_tasks: Iterable[str],
    completed_tasks: Iterable[str],
    accepted_exceptions: Iterable[str],
    unresolved_non_blockers: Iterable[str],
    validation_summary: dict[str, Any],
    evidence: Iterable[str],
) -> dict[str, Any]:
    required = sorted(set(required_tasks))
    completed = sorted(set(completed_tasks))
    exceptions = sorted(set(accepted_exceptions))
    non_blockers = sorted(set(unresolved_non_blockers))
    evidence_items = sorted(set(evidence))
    if not isinstance(validation_summary, dict) or validation_summary.get("status") != "PASS":
        raise HaaContractError("INVALID_VALIDATION_SUMMARY")
    if required != completed:
        raise HaaContractError("REQUIRED_TASKS_NOT_COMPLETED")
    if not isinstance(final_commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", final_commit_sha):
        raise HaaContractError("INVALID_FINAL_COMMIT_SHA")
    return {
        "schema": "workflow.plan-closure-manifest.v1",
        "repository": _required_string(repository, "REPOSITORY"),
        "planId": _required_string(plan_id, "PLAN_ID"),
        "planVersion": _required_string(plan_version, "PLAN_VERSION"),
        "branch": _required_string(branch, "BRANCH"),
        "finalCommitSha": _required_string(final_commit_sha, "FINAL_COMMIT_SHA"),
        "requiredTasks": required,
        "completedTasks": completed,
        "acceptedExceptions": exceptions,
        "unresolvedNonBlockers": non_blockers,
        "validationSummary": validation_summary,
        "evidence": evidence_items,
    }


def build_plan_close_action(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != "workflow.plan-closure-manifest.v1":
        raise HaaContractError("INVALID_PLAN_CLOSURE_MANIFEST")
    validation = manifest.get("validationSummary")
    if not isinstance(validation, dict) or validation.get("status") != "PASS":
        raise HaaContractError("INVALID_VALIDATION_SUMMARY")
    required = manifest.get("requiredTasks")
    completed = manifest.get("completedTasks")
    exceptions = manifest.get("acceptedExceptions")
    evidence = manifest.get("evidence")
    if not all(isinstance(value, list) for value in (required, completed, exceptions, evidence)):
        raise HaaContractError("INVALID_PLAN_CLOSURE_MANIFEST")
    if required != completed:
        raise HaaContractError("REQUIRED_TASKS_NOT_COMPLETED")
    return {
        "schema": "haa.action.v1",
        "type": "workflow.plan.close.v1",
        "payload": {
            "repository": _required_string(manifest.get("repository"), "REPOSITORY"),
            "planId": _required_string(manifest.get("planId"), "PLAN_ID"),
            "branch": _required_string(manifest.get("branch"), "BRANCH"),
            "finalCommitSha": _required_string(manifest.get("finalCommitSha"), "FINAL_COMMIT_SHA"),
            "closureManifestDigest": digest_json(manifest),
            "requiredTaskCount": len(required),
            "completedTaskCount": len(completed),
            "acceptedExceptionCount": len(exceptions),
            "validationStatus": "PASS",
            "evidenceDigest": digest_json(evidence),
        },
    }


def task_start_actual_state(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload")
    if not isinstance(payload, dict) or action.get("type") != "workflow.task.start.v1":
        raise HaaContractError("INVALID_TASK_START_ACTION")
    return {
        "repository": payload["repository"],
        "planId": payload["planId"],
        "taskId": payload["taskId"],
        "sessionId": payload["sessionId"],
        "branch": payload["branch"],
        "currentHead": payload["baseCommitSha"],
        "scopeDigest": payload["scopeDigest"],
    }


def plan_close_actual_state(action: dict[str, Any]) -> dict[str, Any]:
    payload = action.get("payload")
    if not isinstance(payload, dict) or action.get("type") != "workflow.plan.close.v1":
        raise HaaContractError("INVALID_PLAN_CLOSE_ACTION")
    return {
        "workflowState": "PLAN_READY_FOR_APPROVAL",
        "repository": payload["repository"],
        "planId": payload["planId"],
        "branch": payload["branch"],
        "finalCommitSha": payload["finalCommitSha"],
        "closureManifestDigest": payload["closureManifestDigest"],
        "requiredTaskCount": payload["requiredTaskCount"],
        "completedTaskCount": payload["completedTaskCount"],
        "acceptedExceptionCount": payload["acceptedExceptionCount"],
        "validationStatus": payload["validationStatus"],
        "evidenceDigest": payload["evidenceDigest"],
    }
