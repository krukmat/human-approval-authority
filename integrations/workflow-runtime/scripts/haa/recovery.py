"""W3.T3.7: restart-safe, non-authorizing HAA recovery.

Recovery only observes/stops/revokes. It NEVER creates a request, retries
authorizeAndConsume, activates a lease, or resumes an agent runner. Terminal
and ambiguous attempts require a fresh, explicit operator decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.haa.authority_lease import LeaseError, LeaseStore
from scripts.haa.request_checkpoint import (
    Checkpoint, CheckpointError, CheckpointStore, reconcile_status,
)


@dataclass(frozen=True)
class RecoveryResult:
    identity: str
    kind: str
    outcome: str
    state: str
    detail: str


def _ids_from(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def _outcome(state: str) -> tuple[str, str]:
    if state == "WAITING_FOR_HUMAN":
        return ("WAITING_FOR_HUMAN", "Remote request may still require Touch ID")
    if state == "APPROVED_NOT_CONSUMED":
        return ("HOLD_FOR_TRUSTED_EXECUTOR", "Approval is not execution authority")
    if state == "VERIFIED_NO_SIDE_EFFECT":
        return ("HOLD_FOR_LEASE_REVALIDATION", "No side effect or new lease is implied")
    if state in {"PREPARED", "REQUEST_UNCERTAIN"}:
        return ("OPERATOR_RECONCILIATION", "Request POST outcome cannot be proven")
    if state in {"CONSUMPTION_IN_FLIGHT", "CONSUMED_UNVERIFIED"}:
        return ("OPERATOR_RECONCILIATION", "HAA consumption may have happened")
    return ("BLOCKED", "Terminal or revoked authorization")


def revoke_leases_for_attempt(leases: LeaseStore, attempt: Checkpoint) -> tuple[str, ...]:
    """Revoke any lease bound to a cancelled/rejected/uncertain request.

    Cannot silently ignore a malformed or unverifiable sealed lease. The
    future runner must fail closed if this operation raises.
    """
    leases._ensure()
    matching = []
    for lease_id in _ids_from(leases.directory):
        lease = leases.load(lease_id)
        if (
            attempt.request_id is not None
            and lease.request_id == attempt.request_id
        ) or lease.execution_id == attempt.execution_id:
            leases.revoke(lease_id)
            matching.append(lease_id)
    return tuple(matching)


def recover_attempt(
    requester: Any,
    checkpoints: CheckpointStore,
    attempt_id: str,
    *,
    leases: LeaseStore | None = None,
) -> RecoveryResult:
    """Reconcile a single checkpoint without creating any HAA authority.

    PREPARED may represent a crash before or after remote request creation;
    CONSUMPTION_IN_FLIGHT may represent a crash during or after consumption.
    On restart both states are conservatively converted to terminal holds.
    """
    checkpoint = checkpoints.load(attempt_id)
    if checkpoint.status == "PREPARED":
        checkpoint = checkpoints.transition(
            attempt_id, "PREPARED", "REQUEST_UNCERTAIN",
        )
    elif checkpoint.status == "CONSUMPTION_IN_FLIGHT":
        checkpoint = checkpoints.transition(
            attempt_id, "CONSUMPTION_IN_FLIGHT", "CONSUMED_UNVERIFIED",
        )
    elif checkpoint.status in {"WAITING_FOR_HUMAN", "APPROVED_NOT_CONSUMED"}:
        try:
            checkpoint = reconcile_status(requester, checkpoints, attempt_id)
        except Exception as exc:
            # GET is safe to repeat; the attempt remains non-authorizing
            # until remote state/audience/digest can be validated.
            return RecoveryResult(
                identity=attempt_id, kind="attempt",
                outcome="REMOTE_STATUS_UNAVAILABLE",
                state=checkpoint.status,
                detail=type(exc).__name__,
            )

    if leases is not None and checkpoint.status in {
        "REQUEST_UNCERTAIN", "CONSUMED_UNVERIFIED",
        "REJECTED", "REVOKED", "EXPIRED", "CANCELLED_LOCAL", "WAIT_TIMED_OUT",
    }:
        revoke_leases_for_attempt(leases, checkpoint)
    outcome, detail = _outcome(checkpoint.status)
    return RecoveryResult(
        identity=attempt_id, kind="attempt",
        outcome=outcome, state=checkpoint.status, detail=detail,
    )


def recover_all_attempts(
    requester: Any,
    checkpoints: CheckpointStore,
    *,
    leases: LeaseStore | None = None,
) -> list[RecoveryResult]:
    """Return a per-attempt recovery report; no result authorizes execution."""
    checkpoints._dir()
    results = []
    for attempt_id in _ids_from(checkpoints.directory):
        try:
            result = recover_attempt(
                requester, checkpoints, attempt_id, leases=leases,
            )
        except Exception as exc:
            result = RecoveryResult(
                identity=attempt_id, kind="attempt", outcome="BLOCKED",
                state="UNKNOWN", detail=type(exc).__name__,
            )
        results.append(result)
    return results


def recover_all_leases(
    leases: LeaseStore,
    *,
    now: datetime | None = None,
) -> list[RecoveryResult]:
    """Inspect persisted HMAC-sealed leases without returning ALLOW.

    Intact active leases are only candidates for a later W3.T3.6 live guard
    check under the trusted operation lock. Expired leases are revoked.
    """
    leases._ensure()
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise LeaseError("INVALID_RECOVERY_CLOCK")
    current = current.astimezone(UTC)
    results = []
    for lease_id in _ids_from(leases.directory):
        try:
            lease = leases.load(lease_id)
            if lease.status == "REVOKED":
                outcome = "BLOCKED"
                detail = "Previously revoked"
            elif current < datetime.fromisoformat(lease.issued_at).astimezone(UTC):
                lease = leases.revoke(lease_id)
                outcome = "NOT_YET_VALID_REVOKED"
                detail = "Clock precedes lease issuance"
            elif current >= datetime.fromisoformat(lease.expires_at).astimezone(UTC):
                lease = leases.revoke(lease_id)
                outcome = "EXPIRED_REVOKED"
                detail = "Expired during downtime"
            else:
                outcome = "NEEDS_LIVE_SCOPE_CHECK"
                detail = "Must pass W3.T3.6 guard before any operation"
            results.append(RecoveryResult(
                identity=lease_id, kind="lease",
                outcome=outcome, state=lease.status, detail=detail,
            ))
        except Exception as exc:
            results.append(RecoveryResult(
                identity=lease_id, kind="lease",
                outcome="BLOCKED", state="UNKNOWN",
                detail=type(exc).__name__,
            ))
    return results
