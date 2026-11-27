"""W3.T3.3: durable HAA request correlation, not execution authority.

Never retry an uncertain HAA request automatically: the remote POST may have
succeeded even when its response was lost. Checkpoints contain no credentials
and never substitute for a detached-verifiable ExecutionGrant.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from scripts.haa.authority import request_exact_action
from scripts.haa.contracts import canonicalize, digest_json

SCHEMA = "workflow.haa-checkpoint.v1"
ID = re.compile(r"[0-9a-f]{32}\Z")
NEXT = {
    "PREPARED": {"WAITING_FOR_HUMAN", "REQUEST_UNCERTAIN"},
    "REQUEST_UNCERTAIN": set(),
    "WAITING_FOR_HUMAN": {
        "WAITING_FOR_HUMAN", "APPROVED_NOT_CONSUMED", "REJECTED",
        "REVOKED", "EXPIRED", "CONSUMED_UNVERIFIED",
        "CANCELLED_LOCAL", "WAIT_TIMED_OUT",
    },
    "APPROVED_NOT_CONSUMED": {
        "APPROVED_NOT_CONSUMED", "CONSUMPTION_IN_FLIGHT",
        "REJECTED", "REVOKED", "EXPIRED", "CONSUMED_UNVERIFIED",
        "CANCELLED_LOCAL", "WAIT_TIMED_OUT",
    },
    # Must be persisted BEFORE authorizeAndConsume is attempted.
    "CONSUMPTION_IN_FLIGHT": {
        "VERIFIED_NO_SIDE_EFFECT", "CONSUMED_UNVERIFIED",
    },
    "REJECTED": set(), "REVOKED": set(), "EXPIRED": set(),
    "CANCELLED_LOCAL": set(), "WAIT_TIMED_OUT": set(),
    "CONSUMED_UNVERIFIED": set(), "VERIFIED_NO_SIDE_EFFECT": set(),
}


class CheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class Checkpoint:
    attempt_id: str
    execution_id: str
    action_digest: str
    audience: str
    plan_id: str
    task_id: str
    session_id: str
    rri: int
    status: str = "PREPARED"
    request_id: str | None = None

    def record(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **vars(self)}

    @classmethod
    def parse(cls, payload: Any) -> "Checkpoint":
        if not isinstance(payload, dict) or set(payload) != (set(cls.__dataclass_fields__) | {"schema"}):
            raise CheckpointError("INVALID_CHECKPOINT_SHAPE")
        if payload.get("schema") != SCHEMA:
            raise CheckpointError("INVALID_CHECKPOINT_SCHEMA")
        obj = cls(**{key: payload[key] for key in cls.__dataclass_fields__})
        if (
            not all(isinstance(v, str) and ID.fullmatch(v) for v in (obj.attempt_id, obj.execution_id))
            or not all(isinstance(v, str) and v for v in (
                obj.action_digest, obj.audience, obj.plan_id, obj.task_id, obj.session_id
            ))
            or isinstance(obj.rri, bool) or not isinstance(obj.rri, int) or obj.rri < 0
            or obj.status not in NEXT
            or (obj.request_id is not None and not isinstance(obj.request_id, str))
            or (obj.status not in {"PREPARED", "REQUEST_UNCERTAIN"} and not obj.request_id)
        ):
            raise CheckpointError("INVALID_CHECKPOINT_CONTENT")
        return obj


class CheckpointStore:
    def __init__(self, directory: str | Path, *, signing_key: bytes | None = None):
        if signing_key is not None and (not isinstance(signing_key, bytes) or len(signing_key) < 32):
            raise CheckpointError("CHECKPOINT_SIGNING_KEY_INVALID")
        self.directory = Path(directory)
        self._key = signing_key

    @property
    def authenticated(self) -> bool:
        return self._key is not None

    def _mac(self, record: dict[str, Any]) -> str:
        if self._key is None:
            raise CheckpointError("CHECKPOINT_SIGNING_KEY_REQUIRED")
        return hmac.new(self._key, canonicalize(record).encode("utf-8"), sha256).hexdigest()

    def _dir(self) -> None:
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        if (self.directory.is_symlink() or not self.directory.is_dir()
                or self.directory.stat().st_mode & 0o077):
            raise CheckpointError("UNSAFE_STORE_PERMISSIONS")

    def _file(self, attempt_id: str) -> Path:
        if not isinstance(attempt_id, str) or not ID.fullmatch(attempt_id):
            raise CheckpointError("INVALID_ATTEMPT_ID")
        return self.directory / (attempt_id + ".json")

    def _write(self, item: Checkpoint, *, create: bool) -> None:
        target = self._file(item.attempt_id)
        fd, temp = tempfile.mkstemp(dir=self.directory, prefix=".haa-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                record = item.record()
                if self.authenticated:
                    record = {**record, "mac": self._mac(record)}
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            if create:
                try:
                    os.link(temp, target)
                except FileExistsError as exc:
                    raise CheckpointError("CHECKPOINT_ALREADY_EXISTS") from exc
            else:
                if target.is_symlink():
                    raise CheckpointError("UNSAFE_CHECKPOINT_FILE")
                os.replace(temp, target)
            dirfd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def load(self, attempt_id: str) -> Checkpoint:
        self._dir()
        path = self._file(attempt_id)
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise CheckpointError("UNSAFE_CHECKPOINT_FILE")
        record = json.loads(path.read_text(encoding="utf-8"))
        if self.authenticated:
            if not isinstance(record, dict):
                raise CheckpointError("CHECKPOINT_INTEGRITY_FAILED")
            mac = record.pop("mac", None)
            if not isinstance(mac, str) or not hmac.compare_digest(mac, self._mac(record)):
                raise CheckpointError("CHECKPOINT_INTEGRITY_FAILED")
        item = Checkpoint.parse(record)
        if item.session_id.startswith("wfs1-") and not self.authenticated:
            raise CheckpointError("BOUND_CHECKPOINT_REQUIRES_MAC")
        if item.attempt_id != attempt_id:
            raise CheckpointError("CHECKPOINT_ID_MISMATCH")
        return item

    def create(self, item: Checkpoint) -> Checkpoint:
        self._dir()
        Checkpoint.parse(item.record())
        bound = item.session_id.startswith("wfs1-")
        if bound and not self.authenticated:
            raise CheckpointError("BOUND_CHECKPOINT_REQUIRES_MAC")
        with (self.directory / ".lock").open("a+") as lock:
            os.chmod(self.directory / ".lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            if bound:
                for path in sorted(self.directory.glob("*.json")):
                    previous = self.load(path.stem)
                    if previous.session_id == item.session_id:
                        raise CheckpointError("BOUND_SESSION_ATTEMPT_ALREADY_EXISTS")
            self._write(item, create=True)
        return item

    def transition(self, attempt_id: str, old: str, new: str, *, request_id: str | None = None) -> Checkpoint:
        self._dir()
        with (self.directory / ".lock").open("a+") as lock:
            os.chmod(self.directory / ".lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            before = self.load(attempt_id)
            if before.status != old or new not in NEXT[old]:
                raise CheckpointError("INVALID_OR_STALE_TRANSITION")
            if request_id is not None and before.request_id not in (None, request_id):
                raise CheckpointError("REQUEST_ID_CHANGED")
            after = replace(before, status=new, request_id=before.request_id or request_id)
            Checkpoint.parse(after.record())
            self._write(after, create=False)
            return after


def create_attempt(requester: Any, store: CheckpointStore, action: dict[str, Any], *,
                   plan_id: str, task_id: str, session_id: str, rri: int) -> Checkpoint:
    audience = getattr(getattr(requester, "config", None), "executor_audience", None)
    if not isinstance(audience, str) or not audience:
        raise CheckpointError("INVALID_REQUESTER_AUDIENCE")
    prepared = Checkpoint(
        uuid4().hex, uuid4().hex, digest_json(action), audience,
        plan_id, task_id, session_id, rri,
    )
    store.create(prepared)
    try:
        remote = request_exact_action(requester, action)
        if (not isinstance(remote.get("id"), str) or not remote["id"]
                or not isinstance(remote.get("intent"), dict)
                or remote["intent"].get("executorAudience") != audience):
            raise CheckpointError("INVALID_REQUEST_BINDING")
        return store.transition(prepared.attempt_id, "PREPARED", "WAITING_FOR_HUMAN", request_id=remote["id"])
    except Exception:
        store.transition(prepared.attempt_id, "PREPARED", "REQUEST_UNCERTAIN")
        raise


def reconcile_status(requester: Any, store: CheckpointStore, attempt_id: str) -> Checkpoint:
    item = store.load(attempt_id)
    if item.status not in {"WAITING_FOR_HUMAN", "APPROVED_NOT_CONSUMED"}:
        return item
    remote = requester.get_request(item.request_id)
    if remote.get("id") != item.request_id or remote.get("actionDigest") != item.action_digest:
        raise CheckpointError("STATUS_DIGEST_MISMATCH")
    intent = remote.get("intent")
    if not isinstance(intent, dict) or intent.get("executorAudience") != item.audience:
        raise CheckpointError("STATUS_AUDIENCE_MISMATCH")
    mapping = {
        "REQUESTED": "WAITING_FOR_HUMAN",
        "PENDING": "WAITING_FOR_HUMAN",
        "APPROVED": "APPROVED_NOT_CONSUMED",
        "REJECTED": "REJECTED",
        "REVOKED": "REVOKED",
        "EXPIRED": "EXPIRED",
        "CONSUMED": "CONSUMED_UNVERIFIED",
    }
    status = mapping.get(remote.get("state"))
    if status is None:
        raise CheckpointError("UNKNOWN_HAA_STATUS")
    return store.transition(item.attempt_id, item.status, status)


def stop_waiting(store: CheckpointStore, attempt_id: str, *,
                 reason: str) -> Checkpoint:
    """Locally abandon a known request: never represent this as HAA rejection.

    HAA may still show APPROVED remotely, but a terminal local checkpoint
    cannot be consumed by the trusted Workflow executor.
    """
    mapping = {"USER_CANCELLED": "CANCELLED_LOCAL", "LOCAL_TIMEOUT": "WAIT_TIMED_OUT"}
    if reason not in mapping:
        raise CheckpointError("INVALID_LOCAL_STOP_REASON")
    item = store.load(attempt_id)
    if item.status not in {"WAITING_FOR_HUMAN", "APPROVED_NOT_CONSUMED"}:
        raise CheckpointError("CANNOT_STOP_NON_WAITING_ATTEMPT")
    return store.transition(attempt_id, item.status, mapping[reason])
