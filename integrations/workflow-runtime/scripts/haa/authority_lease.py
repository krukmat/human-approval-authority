"""W3.T3.5: scoped internal AuthorityLease (pre-enforcement).

A lease is NOT an HAA grant. It is created only in the trusted executor
process after a fresh, detached-verified HAA task-start consumption.
It cannot authorize external effects or plan closure and is never handed
to an agent as a bearer capability.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import fcntl
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from scripts.haa.contracts import canonicalize, digest_json
from scripts.haa.live_verify import (
    TrustedAuthorityPin, TrustedTask, live_task_action, verify_live_task_authorization,
)
from scripts.haa.request_checkpoint import CheckpointStore

SCHEMA = "workflow.authority-lease.v1"
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STATUSES = {"ACTIVE", "REVOKED"}
_PROTECTED = {"push", "merge", "create_pr", "deploy", "release", "secrets", "delete",
              "overwrite", "migration", "external_call", "plan_close"}
_ALLOWED_CAPABILITIES = {"edit", "test", "review", "commit"}


class LeaseError(RuntimeError):
    pass


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise LeaseError("INVALID_LEASE_TIME")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LeaseError("INVALID_LEASE_TIME") from exc
    if result.tzinfo is None:
        raise LeaseError("INVALID_LEASE_TIME")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class AuthorityLease:
    lease_id: str
    request_id: str
    execution_id: str
    action_digest: str
    repository: str
    plan_id: str
    task_id: str
    session_id: str
    branch: str
    base_commit_sha: str
    scope_digest: str
    allowed_paths: tuple[str, ...]
    capabilities: tuple[str, ...]
    rri: int
    issued_at: str
    expires_at: str
    status: str = "ACTIVE"
    grant_digest: str | None = None

    def record(self) -> dict[str, Any]:
        value = {"schema": SCHEMA, **vars(self)}
        value["allowed_paths"] = list(self.allowed_paths)
        value["capabilities"] = list(self.capabilities)
        return value

    @classmethod
    def parse(cls, record: Any) -> "AuthorityLease":
        if not isinstance(record, dict) or set(record) != set(cls.__dataclass_fields__) | {"schema"}:
            raise LeaseError("INVALID_LEASE_SHAPE")
        if record.get("schema") != SCHEMA:
            raise LeaseError("INVALID_LEASE_SCHEMA")
        fields = {key: record[key] for key in cls.__dataclass_fields__}
        if not isinstance(fields["allowed_paths"], list) or not isinstance(fields["capabilities"], list):
            raise LeaseError("INVALID_LEASE_SCOPE")
        fields["allowed_paths"] = tuple(fields["allowed_paths"])
        fields["capabilities"] = tuple(fields["capabilities"])
        result = cls(**fields)
        strings = (
            result.request_id, result.execution_id, result.action_digest,
            result.repository, result.plan_id, result.task_id, result.session_id,
            result.branch, result.base_commit_sha, result.scope_digest,
        )
        if (
            not isinstance(result.lease_id, str) or not HEX_ID.fullmatch(result.lease_id)
            or any(not isinstance(value, str) or not value for value in strings)
            or len(result.base_commit_sha) != 40
            or any(c not in "0123456789abcdef" for c in result.base_commit_sha)
            or not result.allowed_paths or not result.capabilities
            or any(not isinstance(p, str) or not p or p.startswith("/")
                   or "\\" in p or any(v in {"", ".", ".."} for v in p.split("/"))
                   for p in result.allowed_paths)
            or set(result.capabilities) - _ALLOWED_CAPABILITIES
            or tuple(sorted(set(result.allowed_paths))) != result.allowed_paths
            or tuple(sorted(set(result.capabilities))) != result.capabilities
            or isinstance(result.rri, bool) or not isinstance(result.rri, int)
            or result.rri < 0 or result.status not in _STATUSES
            or (result.grant_digest is not None and (not isinstance(result.grant_digest, str)
                or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}", result.grant_digest)))
        ):
            raise LeaseError("INVALID_LEASE_CONTENT")
        start, end = _timestamp(result.issued_at), _timestamp(result.expires_at)
        if not timedelta(seconds=60) <= end - start <= timedelta(minutes=30):
            raise LeaseError("INVALID_LEASE_TTL")
        return result


class LeaseStore:
    """Private HMAC-authenticated local storage. HMAC key stays executor-only."""

    def __init__(self, directory: Path, *, signing_key: bytes):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise LeaseError("LEASE_SIGNING_KEY_REQUIRED")
        self.directory = Path(directory)
        self._key = signing_key

    def _ensure(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (
            self.directory.is_symlink() or not self.directory.is_dir()
            or self.directory.stat().st_mode & 0o077
        ):
            raise LeaseError("UNSAFE_LEASE_DIRECTORY")

    def _file(self, lease_id: str) -> Path:
        if not isinstance(lease_id, str) or not HEX_ID.fullmatch(lease_id):
            raise LeaseError("INVALID_LEASE_ID")
        return self.directory / (lease_id + ".json")

    def _seal(self, lease: AuthorityLease) -> bytes:
        record = lease.record()
        signature = hmac.new(self._key, canonicalize(record).encode("utf-8"), sha256).hexdigest()
        return (json.dumps({**record, "mac": signature}, sort_keys=True) + "\n").encode()

    def _write(self, lease: AuthorityLease, *, create: bool) -> None:
        path = self._file(lease.lease_id)
        fd, tmp = tempfile.mkstemp(prefix=".lease-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(self._seal(lease))
                stream.flush()
                os.fsync(stream.fileno())
            if create:
                try:
                    os.link(tmp, path)
                except FileExistsError as exc:
                    raise LeaseError("LEASE_ALREADY_EXISTS") from exc
            else:
                if path.is_symlink():
                    raise LeaseError("UNSAFE_LEASE_FILE")
                os.replace(tmp, path)
            dirfd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def create(self, lease: AuthorityLease) -> AuthorityLease:
        self._ensure()
        AuthorityLease.parse(lease.record())
        with (self.directory / ".lock").open("a+") as lock:
            os.chmod(self.directory / ".lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            # A request/execution authorizes ONE lease, even after expiry or
            # revocation. Serialize the uniqueness check with the write.
            for existing_path in sorted(self.directory.glob("*.json")):
                existing = self.load(existing_path.stem)
                if existing.lease_id == lease.lease_id:
                    raise LeaseError("LEASE_ALREADY_EXISTS")
                if (existing.request_id == lease.request_id
                        or existing.execution_id == lease.execution_id):
                    raise LeaseError("LEASE_AUTHORIZATION_ALREADY_USED")
            self._write(lease, create=True)
        return lease

    def load(self, lease_id: str) -> AuthorityLease:
        self._ensure()
        path = self._file(lease_id)
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise LeaseError("UNSAFE_LEASE_FILE")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, TypeError) as exc:
            raise LeaseError("INVALID_LEASE_JSON") from exc
        if not isinstance(envelope, dict) or "mac" not in envelope:
            raise LeaseError("INVALID_LEASE_MAC")
        signature = envelope.pop("mac")
        if not isinstance(signature, str) or not _SHA256.fullmatch(signature):
            raise LeaseError("INVALID_LEASE_MAC")
        expected = hmac.new(self._key, canonicalize(envelope).encode("utf-8"), sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise LeaseError("LEASE_INTEGRITY_FAILED")
        lease = AuthorityLease.parse(envelope)
        if lease.lease_id != lease_id:
            raise LeaseError("LEASE_ID_MISMATCH")
        return lease

    def revoke(self, lease_id: str) -> AuthorityLease:
        self._ensure()
        with (self.directory / ".lock").open("a+") as lock:
            os.chmod(self.directory / ".lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            lease = self.load(lease_id)
            if lease.status == "REVOKED":
                return lease
            replacement = replace(lease, status="REVOKED")
            self._write(replacement, create=False)
            return replacement


def activate_verified_task_lease(
    *, executor: Any, checkpoints: CheckpointStore, leases: LeaseStore,
    attempt_id: str, trusted_task: TrustedTask, authority_pin: TrustedAuthorityPin,
    now: datetime | None = None,
) -> AuthorityLease:
    """Single trusted-process authorization -> local lease activation.

    Never accept a caller-supplied "verified" dict, receipt or HAA grant.
    Failure after HAA consumption leaves checkpoint verified but no lease,
    requiring explicit operator recovery rather than silent re-consumption.
    """
    if now is not None and now.tzinfo is None:
        raise LeaseError("INVALID_LEASE_CLOCK")
    verified = verify_live_task_authorization(
        executor, checkpoints, attempt_id, task=trusted_task, pin=authority_pin,
    )
    if verified.get("status") != "VERIFIED_NO_SIDE_EFFECT":
        raise LeaseError("HAA_GRANT_NOT_VERIFIED")
    checkpoint = checkpoints.load(attempt_id)
    if checkpoint.status != "VERIFIED_NO_SIDE_EFFECT":
        raise LeaseError("CHECKPOINT_NOT_VERIFIED")
    action, _, rri = live_task_action(trusted_task)
    if (
        digest_json(action) != checkpoint.action_digest
        or action["payload"]["planId"] != checkpoint.plan_id
        or action["payload"]["taskId"] != checkpoint.task_id
        or action["payload"]["sessionId"] != checkpoint.session_id
        or rri != checkpoint.rri
    ):
        raise LeaseError("LEASE_ACTIVATION_STATE_CHANGED")
    grant_digest = verified.get("grantDigest")
    if trusted_task.card_sha256 is not None and not grant_digest:
        raise LeaseError("VERIFIED_GRANT_DIGEST_REQUIRED")
    p = action["payload"]
    issued = (now or datetime.now(UTC)).astimezone(UTC)
    expires = issued + timedelta(seconds=p["leaseTtlSeconds"])
    lease = AuthorityLease(
        lease_id=uuid4().hex,
        request_id=checkpoint.request_id,
        execution_id=checkpoint.execution_id,
        action_digest=checkpoint.action_digest,
        repository=p["repository"], plan_id=p["planId"], task_id=p["taskId"],
        session_id=p["sessionId"], branch=p["branch"],
        base_commit_sha=p["baseCommitSha"], scope_digest=p["scopeDigest"],
        allowed_paths=tuple(p["allowedPaths"]), capabilities=tuple(p["capabilities"]),
        rri=rri, issued_at=issued.isoformat(), expires_at=expires.isoformat(),
        grant_digest=grant_digest,
    )
    return leases.create(lease)
