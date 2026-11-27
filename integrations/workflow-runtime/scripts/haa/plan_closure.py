"""W4 candidate closure transaction, deliberately not connected to real plan ledgers.

A trusted controller must read the live canonical workflow snapshot. This
module must not be invoked with agent-authored state or HAA action-derived
preconditions. The journal records candidate closure only; it never modifies
Markdown ledgers, Git or an actual production workflow.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import fcntl
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from uuid import uuid4

from scripts.haa.authority import request_exact_action
from scripts.haa.contracts import (
    build_plan_closure_manifest, build_plan_close_action, canonicalize, digest_json,
)
from scripts.haa.grants import verify_execution_grant
from scripts.haa.live_verify import TrustedAuthorityPin, _git, _pinned_active_authority_key


class ClosureError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanSnapshot:
    workflow_state: str
    plan_id: str
    plan_version: str
    required_tasks: tuple[str, ...]
    completed_tasks: tuple[str, ...]
    accepted_exceptions: tuple[str, ...]
    unresolved_non_blockers: tuple[str, ...]
    validation_summary: dict[str, Any]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ClosureSource:
    repo_root: Path
    repository: str
    plan_id: str
    read_snapshot: Callable[[], PlanSnapshot]


def _unique_nonempty_strings(items: tuple[str, ...], *, required: bool = False):
    if (not isinstance(items, tuple) or (required and not items)
            or any(not isinstance(item, str) or not item for item in items)
            or len(set(items)) != len(items)):
        raise ClosureError("INVALID_PLAN_SNAPSHOT_ITEMS")


def live_closure(source: ClosureSource) -> tuple[dict, dict, dict]:
    """Read a trusted snapshot and actual repository state on every call."""
    snapshot = source.read_snapshot()
    if (not isinstance(snapshot, PlanSnapshot)
            or snapshot.workflow_state != "PLAN_READY_FOR_APPROVAL"
            or snapshot.plan_id != source.plan_id):
        raise ClosureError("PLAN_NOT_READY")
    _unique_nonempty_strings(snapshot.required_tasks, required=True)
    _unique_nonempty_strings(snapshot.completed_tasks, required=True)
    _unique_nonempty_strings(snapshot.accepted_exceptions)
    _unique_nonempty_strings(snapshot.unresolved_non_blockers)
    _unique_nonempty_strings(snapshot.evidence, required=True)
    root = source.repo_root.resolve()
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ClosureError("REPOSITORY_ROOT_MISMATCH")
    if _git(root, "remote", "get-url", "origin") not in {
        f"https://github.com/{source.repository}", f"https://github.com/{source.repository}.git",
        f"git@github.com:{source.repository}.git", f"ssh://git@github.com/{source.repository}.git",
    }:
        raise ClosureError("REPOSITORY_ORIGIN_MISMATCH")
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git(root, "rev-parse", "--verify", "HEAD")
    if not branch or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ClosureError("INVALID_GIT_STATE")
    if _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ClosureError("CLOSURE_WORKTREE_NOT_CLEAN")
    if ("head" in snapshot.validation_summary
            and snapshot.validation_summary["head"] != head):
        raise ClosureError("PLAN_VALIDATION_HEAD_STALE")
    manifest = build_plan_closure_manifest(
        repository=source.repository, plan_id=snapshot.plan_id, plan_version=snapshot.plan_version,
        branch=branch, final_commit_sha=head, required_tasks=snapshot.required_tasks,
        completed_tasks=snapshot.completed_tasks, accepted_exceptions=snapshot.accepted_exceptions,
        unresolved_non_blockers=snapshot.unresolved_non_blockers,
        validation_summary=snapshot.validation_summary, evidence=snapshot.evidence,
    )
    action = build_plan_close_action(manifest)
    # Actual-state evidence derives from the fresh trusted source, not
    # from the requested HAA action.
    actual = {
        "workflowState": snapshot.workflow_state,
        "repository": source.repository, "planId": snapshot.plan_id,
        "branch": branch, "finalCommitSha": head,
        "closureManifestDigest": digest_json(manifest),
        "requiredTaskCount": len(snapshot.required_tasks),
        "completedTaskCount": len(snapshot.completed_tasks),
        "acceptedExceptionCount": len(snapshot.accepted_exceptions),
        "validationStatus": snapshot.validation_summary["status"],
        "evidenceDigest": digest_json(sorted(snapshot.evidence)),
    }
    return manifest, action, actual


class ClosureJournal:
    """Private, HMAC-sealed candidate journal, one transaction per plan.

    Terminal/in-flight records cannot be reset or reused automatically.
    A real host isolation boundary is still a prerequisite.
    """
    def __init__(self, directory: Path, *, signing_key: bytes, repository: str, plan_id: str):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ClosureError("CLOSURE_SIGNING_KEY_REQUIRED")
        self.directory = Path(directory)
        self._key = signing_key
        self.identity = digest_json({"repository": repository, "planId": plan_id})
        self.path = self.directory / (sha256(self.identity.encode()).hexdigest() + ".json")

    @contextmanager
    def locked(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (self.directory.is_symlink() or not self.directory.is_dir()
                or self.directory.stat().st_mode & 0o077):
            raise ClosureError("UNSAFE_CLOSURE_DIRECTORY")
        lock = self.path.with_suffix(".lock")
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as stream:
            if os.fstat(stream.fileno()).st_mode & 0o077:
                raise ClosureError("UNSAFE_CLOSURE_LOCK")
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def _mac(self, record):
        return hmac.new(self._key, canonicalize(record).encode(), sha256).hexdigest()

    def load(self):
        if not self.path.exists():
            if self.path.is_symlink():
                raise ClosureError("UNSAFE_CLOSURE_FILE")
            return None
        if self.path.is_symlink() or self.path.stat().st_mode & 0o077:
            raise ClosureError("UNSAFE_CLOSURE_FILE")
        envelope = json.loads(self.path.read_text())
        if not isinstance(envelope, dict):
            raise ClosureError("INVALID_CLOSURE_RECORD")
        mac = envelope.pop("mac", None)
        if (not isinstance(mac, str) or not hmac.compare_digest(mac, self._mac(envelope))
                or envelope.get("identity") != self.identity
                or envelope.get("schema") != "workflow.closure-journal.v1"):
            raise ClosureError("CLOSURE_INTEGRITY_FAILED")
        return envelope

    def _write(self, record):
        if self.path.is_symlink():
            raise ClosureError("UNSAFE_CLOSURE_FILE")
        fd, tmp = tempfile.mkstemp(prefix=".closure-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump({**record, "mac": self._mac(record)}, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
            dfd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _check_identity(source: ClosureSource, journal: ClosureJournal):
    if digest_json({"repository": source.repository, "planId": source.plan_id}) != journal.identity:
        raise ClosureError("CLOSURE_IDENTITY_MISMATCH")


def request_plan_close(*, source: ClosureSource, journal: ClosureJournal, requester: Any):
    """Persist intent before POST; no automatic second request after ambiguity."""
    _check_identity(source, journal)
    with journal.locked():
        if journal.load() is not None:
            raise ClosureError("CLOSURE_ATTEMPT_ALREADY_EXISTS")
        _, action, _ = live_closure(source)
        audience = requester.config.executor_audience
        if not isinstance(audience, str) or not audience:
            raise ClosureError("INVALID_CLOSURE_AUDIENCE")
        record = {
            "schema": "workflow.closure-journal.v1", "identity": journal.identity,
            "state": "REQUEST_IN_FLIGHT", "actionDigest": digest_json(action),
            "executionId": uuid4().hex, "audience": audience,
            "requestId": None, "grantDigest": None,
        }
        journal._write(record)
        try:
            remote = request_exact_action(requester, action)
            if (not isinstance(remote.get("id"), str) or not remote["id"]
                    or not isinstance(remote.get("intent"), dict)
                    or remote["intent"].get("executorAudience") != audience):
                raise ClosureError("INVALID_CLOSURE_REQUEST_BINDING")
            record.update(state="WAITING_FOR_HUMAN", requestId=remote["id"])
        except Exception:
            record["state"] = "REQUEST_UNCERTAIN"
            journal._write(record)
            raise
        journal._write(record)
        return dict(record)


def finalize_plan_close(*, source: ClosureSource, journal: ClosureJournal,
                        executor: Any, pin: TrustedAuthorityPin):
    """Commit PLAN_DONE in the candidate journal only after detached verification."""
    _check_identity(source, journal)
    with journal.locked():
        record = journal.load()
        if not record or record["state"] != "WAITING_FOR_HUMAN":
            raise ClosureError("CLOSURE_NOT_WAITING")
        _, action, actual = live_closure(source)
        if (digest_json(action) != record["actionDigest"]
                or record["audience"] != executor.config.executor_audience):
            raise ClosureError("STALE_CLOSURE_APPROVAL")
        remote = executor.get_request(record["requestId"])
        if (remote.get("id") != record["requestId"]
                or remote.get("actionDigest") != record["actionDigest"]
                or not isinstance(remote.get("intent"), dict)
                or remote["intent"].get("executorAudience") != record["audience"]):
            raise ClosureError("CLOSURE_REMOTE_BINDING_MISMATCH")
        if remote.get("state") in {"REJECTED", "REVOKED", "EXPIRED", "CONSUMED"}:
            record["state"] = "BLOCKED_REMOTE_" + remote["state"]
            journal._write(record)
            raise ClosureError(record["state"])
        if remote.get("state") != "APPROVED":
            raise ClosureError("WAITING_FOR_HUMAN")
        keys = _pinned_active_authority_key(executor.authority_keys(), pin)
        record["state"] = "CONSUMPTION_IN_FLIGHT"
        journal._write(record)
        try:
            grant = executor.authorize(
                request_id=record["requestId"], execution_id=record["executionId"],
                actual_action=action, actual_state=actual,
            )
            verify_execution_grant(
                grant=grant, authority_keys=keys,
                expected_request_id=record["requestId"],
                expected_execution_id=record["executionId"],
                expected_action_digest=record["actionDigest"],
                expected_executor_audience=record["audience"],
            )
            _, fresh_action, fresh_actual = live_closure(source)
            if digest_json(fresh_action) != record["actionDigest"] or fresh_actual != actual:
                raise ClosureError("POST_CONSUMPTION_CLOSURE_DRIFT")
            record["grantDigest"] = digest_json(grant)
        except Exception:
            record["state"] = "CONSUMED_UNVERIFIED"
            journal._write(record)
            raise
        record["state"] = "PLAN_DONE"
        journal._write(record)
        return dict(record)
