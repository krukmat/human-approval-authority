"""Bounded worker-to-executor IPC for ADR-049.

The worker proposes a replacement of ONE existing regular file. It cannot
activate authority, execute commands, choose a lease, commit or close plans.
The controller and target must be in the protected executor domain. The
legacy agent CLI may run on scratch, not the protected target.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
from threading import RLock
from uuid import uuid4

from scripts.haa.runner_authority import RunnerAuthority
from scripts.haa.volatile_authority import VolatileLeaseStore


MAX_MESSAGE = 2 * 1024 * 1024
MAX_CONTENT = 512 * 1024


class BrokerError(RuntimeError):
    pass


def peer_uid(conn: socket.socket) -> int:
    """Use kernel peer credentials, never a JSON-provided identity."""
    if hasattr(conn, "getpeereid"):
        return conn.getpeereid()[0]
    # CPython on macOS exposes LOCAL_PEERCRED through getsockopt on some
    # versions; do not guess a struct layout. Use libc getpeereid directly.
    if os.sys.platform == "darwin":
        import ctypes
        uid, gid = ctypes.c_uint(), ctypes.c_uint()
        libc = ctypes.CDLL(None, use_errno=True)
        getpeereid = libc.getpeereid
        getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint),
                               ctypes.POINTER(ctypes.c_uint)]
        getpeereid.restype = ctypes.c_int
        if getpeereid(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid)):
            raise BrokerError("PEER_IDENTITY_UNAVAILABLE")
        return uid.value
    if hasattr(socket, "SO_PEERCRED"):
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        return struct.unpack("3i", raw)[1]
    raise BrokerError("PEER_IDENTITY_UNAVAILABLE")


def _read_exact(conn, length):
    out = bytearray()
    while len(out) < length:
        part = conn.recv(length - len(out))
        if not part:
            raise BrokerError("TRUNCATED_MESSAGE")
        out.extend(part)
    return bytes(out)


def read_message(conn):
    size = struct.unpack("!I", _read_exact(conn, 4))[0]
    if not 0 < size <= MAX_MESSAGE:
        raise BrokerError("INVALID_MESSAGE_LENGTH")
    def unique(pairs):
        obj = {}
        for key, val in pairs:
            if key in obj:
                raise BrokerError("DUPLICATE_FIELD")
            obj[key] = val
        return obj
    value = json.loads(_read_exact(conn, size).decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise BrokerError("INVALID_MESSAGE")
    return value


def write_message(conn, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(raw) <= MAX_MESSAGE:
        raise BrokerError("INVALID_MESSAGE_LENGTH")
    conn.sendall(struct.pack("!I", len(raw)) + raw)


def _replace_existing(root: Path, path: str, before: str, content: str):
    """Trusted target only; no symlink/hardlink or arbitrary path writes."""
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or any(v in {"", ".", "..", ".git", ".agent"} for v in path.split("/"))):
        raise BrokerError("INVALID_PATCH_PATH")
    if (not isinstance(before, str) or len(before) != 64
            or any(c not in "0123456789abcdef" for c in before)
            or not isinstance(content, str)):
        raise BrokerError("INVALID_PATCH")
    data = content.encode("utf-8")
    if len(data) > MAX_CONTENT:
        raise BrokerError("PATCH_TOO_LARGE")
    target = root / path
    if target.resolve() != target or not target.is_relative_to(root):
        raise BrokerError("UNSAFE_PATCH_PATH")
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o022):
            raise BrokerError("UNSAFE_TARGET_FILE")
        current = stream.read(MAX_CONTENT + 1)
    if len(current) > MAX_CONTENT or sha256(current).hexdigest() != before:
        raise BrokerError("STALE_PREIMAGE")
    fd, tmp = tempfile.mkstemp(prefix=".haa-edit-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode) & 0o755)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Executor-exclusive protected directory is required; this is not
        # a safe write primitive for a shared attacker-writable directory.
        fresh = target.lstat()
        if (fresh.st_dev, fresh.st_ino, fresh.st_size, fresh.st_mtime_ns, fresh.st_ctime_ns) != (
                info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise BrokerError("TARGET_CHANGED")
        os.replace(tmp, target)
        dfd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return sha256(data).hexdigest()


class WorkerBroker:
    """Single trusted session. No owner controls exposed on the worker socket."""
    def __init__(self, authority: RunnerAuthority, *, worker_uid: int):
        if (type(worker_uid) is not int or worker_uid <= 0
                or worker_uid == os.geteuid()):
            raise BrokerError("INVALID_WORKER_IDENTITY")
        if not isinstance(authority.leases, VolatileLeaseStore):
            raise BrokerError("VOLATILE_AUTHORITY_REQUIRED")
        self.authority = authority
        self.worker_uid = worker_uid
        self._window = uuid4().hex
        self._accepted = None
        self._sealed = False
        self._lock = RLock()

    def seal(self):
        """Close the one-proposal window and return trusted edit evidence."""
        with self._lock:
            self._sealed = True
            return self._accepted

    def dispatch(self, uid: int, msg: dict):
        with self._lock:
            if uid != self.worker_uid:
                raise BrokerError("PEER_NOT_AUTHORIZED")
            if not isinstance(msg, dict):
                raise BrokerError("INVALID_MESSAGE")
            if self._sealed or self._accepted is not None:
                raise BrokerError("WORKER_WINDOW_CLOSED")
            if msg == {"op": "status"}:
                # Non-authorizing status; no credentials/lease ID exposed.
                return {"status": "BROKER_REACHABLE", "window": self._window}
            if set(msg) != {"op", "window", "path", "before_sha256", "content"} or msg["op"] != "replace":
                raise BrokerError("UNSUPPORTED_PROPOSAL")
            if msg["window"] != self._window:
                raise BrokerError("STALE_WORKER_WINDOW")
            path = msg["path"]
            if not isinstance(path, str):
                raise BrokerError("INVALID_PATCH_PATH")
            digest = self.authority.edit(path, lambda: _replace_existing(
                self.authority.scope.task.repo_root.resolve(), path,
                msg["before_sha256"], msg["content"]))
            self._accepted = (path, digest)
            return {"status": "REPLACED", "sha256": digest}

    def handle(self, conn: socket.socket):
        conn.settimeout(5)
        try:
            uid = peer_uid(conn)
            if uid != self.worker_uid:
                raise BrokerError("PEER_NOT_AUTHORIZED")
            result = self.dispatch(uid, read_message(conn))
        except Exception:
            # Do not leak private paths, credentials or exception payloads.
            result = {"status": "BLOCKED"}
        write_message(conn, result)


def send_proposal(socket_path: Path, msg: dict):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(10)
        conn.connect(str(socket_path))
        write_message(conn, msg)
        return read_message(conn)
