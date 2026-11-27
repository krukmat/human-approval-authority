"""ADR-049 service-local authority. No disk file can restore an active lease.

Only the protected executor may instantiate this registry or call create.
The existing disk LeaseStore remains historical/synthetic, not production.
A journal stores admission tombstones, never bearer authority.
"""
from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager, closing
from datetime import UTC, datetime
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
from time import monotonic
from uuid import uuid4

from scripts.haa.authority_lease import AuthorityLease, LeaseError


def _private_directory(directory: Path):
    if not directory.is_absolute() or directory != directory.resolve():
        raise LeaseError("UNSAFE_JOURNAL_PATH")
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise LeaseError("UNSAFE_JOURNAL_DIRECTORY")


def _private_file(path: Path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or info.st_nlink != 1):
        raise LeaseError("UNSAFE_JOURNAL_FILE")


class AdmissionJournal:
    """Single-process protected tombstone store. Explicit initialization only.

    Whole-host privileged rollback is out of scope. Local DAC checks are
    necessary but not sufficient; ADR-049 host validation is still required.
    """
    @staticmethod
    def initialize(directory: Path):
        _private_directory(directory)
        path = directory / "admissions.sqlite3"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        # If initialization fails, retain incomplete file and fail closed.
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE admissions (
                request_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL UNIQUE, grant_digest TEXT NOT NULL UNIQUE,
                action_digest TEXT NOT NULL, generation TEXT NOT NULL,
                disposition TEXT NOT NULL CHECK(disposition IN ('ADMITTED','REVOKED'))
            )""")
            db.execute("PRAGMA user_version=1")
        # Never automatically reinitialize a missing or corrupt journal.

    def __init__(self, directory: Path):
        _private_directory(directory)
        self.directory = directory
        self.path = directory / "admissions.sqlite3"
        _private_file(self.path)
        self.lock = os.open(directory / ".service.lock",
                            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(self.lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise LeaseError("UNSAFE_SERVICE_LOCK")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self._connect() as db:
                if db.execute("PRAGMA user_version").fetchone() != (1,):
                    raise LeaseError("UNINITIALIZED_ADMISSION_JOURNAL")
                db.execute("SELECT request_id FROM admissions LIMIT 1")
        except BaseException:
            os.close(self.lock)
            self.lock = None
            raise

    @contextmanager
    def _connect(self):
        if self.lock is None:
            raise LeaseError("JOURNAL_CLOSED")
        _private_file(self.path)
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def admit(self, lease: AuthorityLease, generation: str):
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO admissions VALUES (?,?,?,?,?,?,?)",
                           (lease.request_id, lease.execution_id, lease.session_id,
                            lease.grant_digest, lease.action_digest, generation, "ADMITTED"))
        except sqlite3.IntegrityError as exc:
            raise LeaseError("AUTHORIZATION_ALREADY_ADMITTED") from exc

    def revoke(self, lease: AuthorityLease, generation: str):
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE admissions SET disposition='REVOKED' WHERE request_id=? AND generation=?",
                (lease.request_id, generation))
            if cursor.rowcount != 1:
                raise LeaseError("ADMISSION_NOT_FOUND")

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None


class VolatileLeaseStore:
    """Compatible create/load/revoke seam for trusted activation and guard.

    No restore method, no serialized ACTIVE records, no accepted grant
    originating from IPC. Monotonic deadline is independent of wall rollback.
    A failed journal admission never creates an active lease.
    """
    def __init__(self, journal: AdmissionJournal, *, clock=monotonic, wall=None):
        self.journal = journal
        self.generation = uuid4().hex
        self._clock = clock
        self._wall = wall or (lambda: datetime.now(UTC))
        self._lock = RLock()
        self._live = {}
        self._closed = False

    def _now(self):
        now = self._wall()
        if now.tzinfo is None:
            raise LeaseError("INVALID_SERVICE_CLOCK")
        return now.astimezone(UTC)

    def create(self, lease: AuthorityLease):
        with self._lock:
            if self._closed:
                raise LeaseError("REGISTRY_CLOSED")
            AuthorityLease.parse(lease.record())
            if lease.status != "ACTIVE" or not lease.grant_digest:
                raise LeaseError("VERIFIED_GRANT_REQUIRED")
            now = self._now()
            start, end = datetime.fromisoformat(lease.issued_at), datetime.fromisoformat(lease.expires_at)
            if not start <= now < end or lease.lease_id in self._live:
                raise LeaseError("INVALID_LEASE_ADMISSION")
            deadline = self._clock() + (end - now).total_seconds()
            self.journal.admit(lease, self.generation)
            self._live[lease.lease_id] = (lease, deadline, now)
            return lease

    def load(self, lease_id: str):
        with self._lock:
            if self._closed or lease_id not in self._live:
                raise LeaseError("NO_LIVE_AUTHORITY")
            lease, deadline, last_wall = self._live[lease_id]
            now = self._now()
            if (now < last_wall or now >= datetime.fromisoformat(lease.expires_at)
                    or self._clock() >= deadline):
                self.revoke(lease_id)
                raise LeaseError("LEASE_EXPIRED_OR_CLOCK_ROLLBACK")
            self._live[lease_id] = (lease, deadline, now)
            return lease

    def revoke(self, lease_id: str):
        with self._lock:
            # Remove authority BEFORE durable evidence; errors cannot restore it.
            entry = self._live.pop(lease_id, None)
            if entry is None:
                raise LeaseError("NO_LIVE_AUTHORITY")
            lease = entry[0]
            self.journal.revoke(lease, self.generation)
            return replace(lease, status="REVOKED")

    def close(self):
        with self._lock:
            self._closed = True
            # Admission tombstones already exist. Restart never restores live
            # state, including if the process crashed before recording revoke.
            self._live.clear()
            self.journal.close()
