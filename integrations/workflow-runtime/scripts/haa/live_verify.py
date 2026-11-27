"""W3.T3.4: verify one task-start grant against live Git + trusted card.

PREPARATORY ONLY. Nothing here activates an AuthorityLease, starts a runner,
changes task status, merges, pushes, or closes a plan. The caller must be
the trusted orchestrator; never pass agent-supplied task cards or key pins.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from uuid import uuid4
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts.haa.policy import PolicyPin, PolicyError
from scripts.haa.contracts import build_task_start_action, digest_json
from scripts.haa.grants import verify_execution_grant
from scripts.haa.request_checkpoint import CheckpointError, CheckpointStore


class LiveAuthorityError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrustedTask:
    repo_root: Path
    repository: str
    card_path: Path
    session_id: str
    capabilities: tuple[str, ...]
    lease_ttl_seconds: int = 1800
    card_sha256: str | None = None
    authoritative_rri: int | None = None
    policy_pin: PolicyPin | None = None


@dataclass(frozen=True)
class TrustedAuthorityPin:
    key_id: str
    public_key_pem_sha256: str


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(root), "-c", "core.hooksPath=/dev/null",
             "-c", "core.fsmonitor=false", *args], check=True,
            env={"PATH":"/usr/bin:/bin","HOME":"/var/empty","LANG":"C",
                 "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                 "GIT_NO_REPLACE_OBJECTS":"1","GIT_TERMINAL_PROMPT":"0"},
            text=True, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LiveAuthorityError("LIVE_GIT_STATE_UNAVAILABLE") from exc
    return result.stdout.strip()


def _trusted_card(card_path: Path, root: Path, *, expected_sha256: str | None = None) -> Any:
    resolved = card_path.resolve()
    if not resolved.is_relative_to(root):
        raise LiveAuthorityError("TASK_CARD_OUTSIDE_REPOSITORY")
    if card_path.is_symlink() or not resolved.is_file():
        raise LiveAuthorityError("INVALID_TASK_CARD")
    # Reject symlinked directories inside the repository too. Do not reject
    # OS-level aliases above its root (e.g. /var -> /private/var on macOS).
    for parent in card_path.absolute().parents:
        if not parent.resolve().is_relative_to(root):
            break
        if parent.is_symlink():
            raise LiveAuthorityError("INVALID_TASK_CARD")
    # local-agent is a repository directory rather than a Python package.
    local_dir = str(Path(__file__).resolve().parents[1] / "local-agent")
    if local_dir not in sys.path:
        sys.path.insert(0, local_dir)
    from task_card import parse_task_card

    # Parse the exact bytes whose digest was checked, not a second read.
    fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise LiveAuthorityError("TASK_CARD_TOO_LARGE")
    if expected_sha256 is not None and sha256(raw).hexdigest() != expected_sha256:
        raise LiveAuthorityError("TASK_CARD_DIGEST_CHANGED")
    return parse_task_card(json.loads(raw))


_BOUND_SESSION = re.compile(r"wfs1-([0-9a-f]{32})-([0-9a-f]{64})\Z")


def _session_digest(nonce: str, card_sha256: str, rri: int, policy_pin: PolicyPin | None = None) -> str:
    # sessionId and scopeDigest are already bound by the HAA v1 action
    # digest. No HAA wire/profile migration is necessary.
    return sha256(f"workflow-task-session-v1:{nonce}:{card_sha256}:{rri}:{policy_pin.digest() if policy_pin else 'legacy-fixture'}".encode()).hexdigest()


def bind_trusted_task(task: TrustedTask, *, card_sha256: str, authoritative_rri: int,
                      policy_pin: PolicyPin | None = None) -> TrustedTask:
    """Called ONLY by a trusted supervisor with independently obtained RRI/card pin.

    This function is not a calculator, approval or proof of OS isolation.
    The original task session is replaced by a new digest-bound session.
    """
    if (not isinstance(card_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", card_sha256)
            or type(authoritative_rri) is not int or authoritative_rri < 0):
        raise LiveAuthorityError("INVALID_TRUSTED_CARD_PIN_OR_RRI")
    card = _trusted_card(task.card_path, task.repo_root.resolve(), expected_sha256=card_sha256)
    if card.rri != authoritative_rri:
        raise LiveAuthorityError("AUTHORITATIVE_RRI_MISMATCH")
    if policy_pin is not None:
        _check_policy_pin(policy_pin, task, card_sha256, authoritative_rri)
    nonce = uuid4().hex
    return replace(task, session_id=f"wfs1-{nonce}-{_session_digest(nonce, card_sha256, authoritative_rri, policy_pin)}",
                   card_sha256=card_sha256, authoritative_rri=authoritative_rri, policy_pin=policy_pin)


def _check_policy_pin(pin, task, card_sha256, rri):
    if not isinstance(pin, PolicyPin):
        raise LiveAuthorityError("INVALID_POLICY_PIN")
    try:
        pin.validate(root=task.repo_root, repository=task.repository,
                     card_sha256=card_sha256, rri=rri, capabilities=task.capabilities)
    except (PolicyError, TypeError, ValueError, OSError) as exc:
        raise LiveAuthorityError("POLICY_PIN_INVALID_OR_CHANGED") from exc


def task_requires_haa(task, card):
    # Legacy isolated regressions use the previous RRI fixture path only.
    # ProtectedSession and volatile admission require an explicit policy pin.
    return task.policy_pin.requires_haa if task.policy_pin is not None else card.rri > 25


def checked_bound_card(task: TrustedTask, root: Path, *, required: bool = False) -> Any:
    # Legacy smoke/unit paths may remain unbound; candidate runtime MUST
    # explicitly require a digest-bound session.
    if task.card_sha256 is None and task.authoritative_rri is None:
        if task.policy_pin is not None:
            raise LiveAuthorityError("BOUND_POLICY_REQUIRED")
        if required or _BOUND_SESSION.fullmatch(task.session_id):
            raise LiveAuthorityError("BOUND_TASK_REQUIRED")
        return _trusted_card(task.card_path, root)
    if task.policy_pin is not None:
        _check_policy_pin(task.policy_pin, task, task.card_sha256, task.authoritative_rri)
    match = _BOUND_SESSION.fullmatch(task.session_id)
    if (not match or not isinstance(task.card_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", task.card_sha256)
            or type(task.authoritative_rri) is not int
            or task.authoritative_rri < 0
            or match.group(2) != _session_digest(match.group(1), task.card_sha256, task.authoritative_rri, task.policy_pin)):
        raise LiveAuthorityError("INVALID_BOUND_TASK_SESSION")
    card = _trusted_card(task.card_path, root, expected_sha256=task.card_sha256)
    if card.rri != task.authoritative_rri:
        raise LiveAuthorityError("AUTHORITATIVE_RRI_MISMATCH")
    return card


def live_task_action(task: TrustedTask) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Rebuild independently from a validated card and actual Git state."""
    root = task.repo_root.resolve()
    if not root.is_dir() or Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise LiveAuthorityError("REPOSITORY_ROOT_MISMATCH")
    origins = {
        "https://github.com/" + task.repository,
        "https://github.com/" + task.repository + ".git",
        "git@github.com:" + task.repository + ".git",
        "ssh://git@github.com/" + task.repository + ".git",
    }
    if _git(root, "remote", "get-url", "origin") not in origins:
        raise LiveAuthorityError("REPOSITORY_ORIGIN_MISMATCH")
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    if not branch or len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise LiveAuthorityError("INVALID_LIVE_GIT_HEAD")

    card = checked_bound_card(task, root)
    if (
        not isinstance(card.rri, int) or isinstance(card.rri, bool)
        or not task_requires_haa(task, card) or not card.plan
    ):
        raise LiveAuthorityError("UNTRUSTED_TASK_RRI_OR_PLAN")
    plan_id = Path(card.plan).stem
    if not plan_id or not task.session_id:
        raise LiveAuthorityError("MISSING_TRUSTED_CONTEXT")

    # Do not use action-derived W2 smoke helpers as current-state evidence.
    action = build_task_start_action(
        repository=task.repository,
        plan_id=plan_id,
        task_id=card.task_id,
        session_id=task.session_id,
        branch=branch,
        base_commit_sha=head,
        allowed_paths=card.allowed_paths,
        capabilities=task.capabilities,
        lease_ttl_seconds=task.lease_ttl_seconds,
    )
    payload = action["payload"]
    actual_state = {
        "repository": task.repository,
        "planId": plan_id,
        "taskId": card.task_id,
        "sessionId": task.session_id,
        "branch": branch,
        "currentHead": head,
        "scopeDigest": payload["scopeDigest"],
    }
    return action, actual_state, card.rri


def _pinned_active_authority_key(keys: Any, pin: TrustedAuthorityPin) -> list[dict[str, Any]]:
    if not (
        isinstance(pin.key_id, str) and pin.key_id
        and isinstance(pin.public_key_pem_sha256, str)
        and len(pin.public_key_pem_sha256) == 64
        and all(c in "0123456789abcdef" for c in pin.public_key_pem_sha256)
    ):
        raise LiveAuthorityError("AUTHORITY_PIN_REQUIRED")
    if not isinstance(keys, list):
        raise LiveAuthorityError("INVALID_AUTHORITY_KEYS")
    matching = [key for key in keys if isinstance(key, dict) and key.get("keyId") == pin.key_id]
    if len(matching) != 1 or matching[0].get("status") != "ACTIVE":
        raise LiveAuthorityError("PINNED_AUTHORITY_KEY_UNAVAILABLE")
    pem = matching[0].get("publicKeyPem")
    if not isinstance(pem, str) or sha256(pem.encode("utf-8")).hexdigest() != pin.public_key_pem_sha256:
        raise LiveAuthorityError("AUTHORITY_KEY_PIN_MISMATCH")
    return matching


def verify_live_task_authorization(
    executor: Any, store: CheckpointStore, attempt_id: str,
    *, task: TrustedTask, pin: TrustedAuthorityPin,
) -> dict[str, str]:
    """Consume a single action and verify detached. No workflow side effects.

    The stable execution ID comes only from the persisted checkpoint. If the
    remote consume succeeds but local verification fails, the checkpoint is
    terminally non-authoritative and no automatic retry is attempted.
    """
    checkpoint = store.load(attempt_id)
    if checkpoint.status != "APPROVED_NOT_CONSUMED":
        raise CheckpointError("REQUEST_NOT_APPROVED_OR_ALREADY_CONSUMED")
    if checkpoint.request_id is None:
        raise CheckpointError("REQUEST_ID_REQUIRED")
    if checkpoint.audience != executor.config.executor_audience:
        raise LiveAuthorityError("EXECUTOR_AUDIENCE_MISMATCH")
    action, state, rri = live_task_action(task)
    if (
        digest_json(action) != checkpoint.action_digest
        or action["payload"]["planId"] != checkpoint.plan_id
        or action["payload"]["taskId"] != checkpoint.task_id
        or action["payload"]["sessionId"] != checkpoint.session_id
        or rri != checkpoint.rri
    ):
        raise LiveAuthorityError("LIVE_TASK_ACTION_STALE")

    remote = executor.get_request(checkpoint.request_id)
    if (
        remote.get("id") != checkpoint.request_id
        or remote.get("actionDigest") != checkpoint.action_digest
        or remote.get("state") != "APPROVED"
        or not isinstance(remote.get("intent"), dict)
        or remote["intent"].get("executorAudience") != checkpoint.audience
    ):
        raise LiveAuthorityError("REMOTE_APPROVAL_BINDING_MISMATCH")

    # Pin must come from an operator-controlled trust store, not HAA's own
    # response, preventing a compromised endpoint from replacing its key.
    trusted_keys = _pinned_active_authority_key(executor.authority_keys(), pin)

    # Durably cross the irreversible boundary before making the HAA
    # authorizeAndConsume HTTP call. A process crash here is conservatively
    # treated as uncertain consumption, never as an approval to retry.
    store.transition(attempt_id, "APPROVED_NOT_CONSUMED", "CONSUMPTION_IN_FLIGHT")
    try:
        grant = executor.authorize(
            request_id=checkpoint.request_id,
            execution_id=checkpoint.execution_id,
            actual_action=action,
            actual_state=state,
        )
        verify_execution_grant(
            grant=grant, authority_keys=trusted_keys,
            expected_request_id=checkpoint.request_id,
            expected_execution_id=checkpoint.execution_id,
            expected_action_digest=checkpoint.action_digest,
            expected_executor_audience=checkpoint.audience,
        )
        fresh_action, _, fresh_rri = live_task_action(task)
        if digest_json(fresh_action) != checkpoint.action_digest or fresh_rri != checkpoint.rri:
            raise LiveAuthorityError("POST_CONSUMPTION_GIT_OR_CARD_DRIFT")
    except Exception:
        # Fail closed after possibly consuming the HAA request. A later
        # restart must not treat the old APPROVED checkpoint as live authority.
        store.transition(attempt_id, "CONSUMPTION_IN_FLIGHT", "CONSUMED_UNVERIFIED")
        raise

    store.transition(attempt_id, "CONSUMPTION_IN_FLIGHT", "VERIFIED_NO_SIDE_EFFECT")
    return {
        "status": "VERIFIED_NO_SIDE_EFFECT",
        "requestId": checkpoint.request_id,
        "executionId": checkpoint.execution_id,
        "actionDigest": checkpoint.action_digest,
        "authorityKeyId": grant["authorityKeyId"],
        "grantDigest": digest_json(grant),
    }
