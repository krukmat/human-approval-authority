"""Pure W3 authority-boundary classifier (NOT an authorization verifier).

The result classifies the need for a human authorization ceremony. It never
certifies that the caller may execute, and it never accepts a caller-asserted
'approved' flag as proof of a valid HAA grant or Workflow AuthorityLease.

Runners must preserve their existing RRI/HITL, scope, and evidence gates until
W3.3–W3.5 attach actual HAA authorization and verify live resource state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scripts.haa.policy import PolicyPin
from scripts.haa.contracts import HaaContractError, build_task_scope

AuthorityOutcome = Literal["ALLOW", "REQUIRE_HAA", "BLOCK"]

# Only existing, versioned ActionProfiles are requestable. Operations without
# an exact-action HAA profile cannot be turned into generic approvals.
_EXACT_PROFILES = {
    "merge": "git.merge.v1",
    "plan_close": "workflow.plan.close.v1",
}
_ROUTINE_OPERATIONS = frozenset({"task_start", "edit", "test", "review", "commit"})
_CAPABILITY_OPERATIONS = frozenset({"edit", "test", "review", "commit"})
_REQUIRES_NEW_PROFILE = frozenset({
    "push", "create_pr", "release", "deploy", "secrets", "delete",
    "overwrite", "migration", "external_call", "privileged_operation",
})


@dataclass(frozen=True)
class TaskScope:
    """Snapshot of trusted workflow inputs, NOT proof of HAA approval."""

    repository: str
    plan_id: str
    task_id: str
    session_id: str
    branch: str
    base_commit_sha: str
    allowed_paths: tuple[str, ...]
    capabilities: tuple[str, ...]
    rri: int


@dataclass(frozen=True)
class AuthorityDecision:
    outcome: AuthorityOutcome
    reason: str
    action_profile: str | None = None


def _checked_scope(scope: TaskScope) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Normalize scope/capabilities using exactly the W2 contract rules."""
    if not isinstance(scope, TaskScope):
        raise HaaContractError("INVALID_TASK_SCOPE")
    if isinstance(scope.rri, bool) or not isinstance(scope.rri, int) or scope.rri < 0:
        raise HaaContractError("INVALID_RRI")
    # W2 validates repository, IDs, paths, and the initial capability set.
    normalized = build_task_scope(
        repository=scope.repository,
        plan_id=scope.plan_id,
        task_id=scope.task_id,
        session_id=scope.session_id,
        branch=scope.branch,
        base_commit_sha=scope.base_commit_sha,
        allowed_paths=scope.allowed_paths,
        capabilities=scope.capabilities,
    )
    return (tuple(normalized["allowedPaths"]), tuple(normalized["capabilities"]))


def _has_scope_drift(current: TaskScope, approved: TaskScope) -> bool:
    current_paths, current_capabilities = _checked_scope(current)
    previous_paths, previous_capabilities = _checked_scope(approved)
    # A new base commit changes the task-start envelope. Follow-on commits
    # within a previously authorized lease belong to W3.5's live verifier,
    # not to a guessed authorization in this pure classifier.
    return (
        current.repository != approved.repository
        or current.plan_id != approved.plan_id
        or current.task_id != approved.task_id
        or current.session_id != approved.session_id
        or current.branch != approved.branch
        or current.base_commit_sha != approved.base_commit_sha
        or current_paths != previous_paths
        or current_capabilities != previous_capabilities
        or current.rri != approved.rri
    )


def evaluate_authority_boundary(
    *,
    operation: str,
    current_scope: TaskScope,
    approved_scope: TaskScope | None = None,
    policy_pin: PolicyPin | None = None,
) -> AuthorityDecision:
    """Classify an operation, without supplying or verifying any authority.

    ALLOW means *no new HAA-specific prompt*; existing task/runner/HITL gates
    still apply. REQUIRE_HAA means acquire and verify exact HAA authority at
    a later integration stage. BLOCK means the action has no supported typed
    HAA path, or its context is invalid. This function makes no I/O.
    """
    try:
        _checked_scope(current_scope)
        if approved_scope is not None:
            _checked_scope(approved_scope)
    except (HaaContractError, TypeError, ValueError):
        return AuthorityDecision("BLOCK", "INVALID_SCOPE")

    if policy_pin is not None and (
        not isinstance(policy_pin, PolicyPin)
        or policy_pin.repository != current_scope.repository
        or policy_pin.rri != current_scope.rri
        or policy_pin.capabilities != tuple(sorted(current_scope.capabilities))
    ):
        return AuthorityDecision("BLOCK", "POLICY_SCOPE_MISMATCH")

    if not isinstance(operation, str) or not operation:
        return AuthorityDecision("BLOCK", "INVALID_OPERATION")

    if operation in _REQUIRES_NEW_PROFILE:
        return AuthorityDecision("BLOCK", "UNSUPPORTED_ACTION_PROFILE")
    if operation not in _ROUTINE_OPERATIONS and operation not in _EXACT_PROFILES:
        return AuthorityDecision("BLOCK", "UNKNOWN_OPERATION")

    if operation == "plan_close":
        if policy_pin is not None and not policy_pin.plan_close_requires_haa:
            return AuthorityDecision("ALLOW", "EXISTING_CLOSURE_POLICY_APPLIES")
        return AuthorityDecision("REQUIRE_HAA", "MANDATORY_PLAN_CLOSURE", _EXACT_PROFILES[operation])
    if operation == "merge":
        return AuthorityDecision("REQUIRE_HAA", "EXACT_PRIVILEGED_ACTION", _EXACT_PROFILES[operation])

    if operation in _CAPABILITY_OPERATIONS and operation not in current_scope.capabilities:
        return AuthorityDecision("BLOCK", "CAPABILITY_OUT_OF_SCOPE")

    # A snapshot is only a drift detector, never a verified HAA grant. It
    # cannot turn a high-RRI REQUIRE_HAA decision into ALLOW.
    if approved_scope is not None and _has_scope_drift(current_scope, approved_scope):
        return AuthorityDecision("REQUIRE_HAA", "SCOPE_OR_RISK_CHANGED", "workflow.task.start.v1")

    # Legacy classifier fallback is for historical synthetic regressions only.
    if (policy_pin.requires_haa if policy_pin is not None else current_scope.rri > 25):
        return AuthorityDecision("REQUIRE_HAA", "RRI_HITL_REQUIRED", "workflow.task.start.v1")

    return AuthorityDecision("ALLOW", "NO_ADDITIONAL_HAA_GATE")
