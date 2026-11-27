"""Protected canonical plan state with atomic closure transaction.

Only the trusted service may initialize/update this store. No Markdown
import, CLI or agent-supplied snapshot is authoritative. Runtime deployment
and actual plan lifecycle wiring remain separate certification requirements.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict, replace
import hmac
import json
import os
import re
from pathlib import Path
import sqlite3

from scripts.haa.plan_closure import (
    ClosureJournal, ClosureError, ClosureSource, PlanSnapshot,
)
from scripts.haa.contracts import canonicalize, digest_json
from scripts.haa.volatile_authority import _private_directory, _private_file


def _snapshot(raw: dict) -> PlanSnapshot:
    result = dict(raw)
    for key in ("required_tasks", "completed_tasks", "accepted_exceptions",
                "unresolved_non_blockers", "evidence"):
        result[key] = tuple(result[key])
    return PlanSnapshot(**result)


class ProtectedPlanJournal(ClosureJournal):
    """One protected canonical plan per database; no implicit initialization.

    The inherited lock serializes snapshot updates and closure. Its _write
    commits the closure record and PLAN_DONE in the SAME SQLite transaction.
    All writers must use this API in the trusted service domain.
    """

    @classmethod
    def initialize(cls, directory: Path, *, signing_key: bytes,
                   repository: str, snapshot: PlanSnapshot):
        if snapshot.workflow_state not in {"ACTIVE", "PLAN_READY_FOR_APPROVAL"}:
            raise ClosureError("INVALID_INITIAL_PLAN_STATE")
        _private_directory(directory)
        journal = cls(directory, signing_key=signing_key, repository=repository,
                      plan_id=snapshot.plan_id, _initializing=True)
        with journal.locked():
            fd = os.open(journal.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with closing(sqlite3.connect(journal.db_path)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("CREATE TABLE plan (id INTEGER PRIMARY KEY CHECK(id=1), identity TEXT NOT NULL, snapshot TEXT NOT NULL, closure TEXT)")
                db.execute("""CREATE TABLE task_attempts (
                    task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL CHECK(state IN ('IN_FLIGHT','COMPLETED','UNCERTAIN')),
                    evidence TEXT
                )""")
                db.execute("PRAGMA user_version=2")
                db.execute("INSERT INTO plan VALUES (1,?,?,NULL)",
                           (journal.identity, canonicalize(json.loads(json.dumps(asdict(snapshot))))))
        return journal

    def __init__(self, directory: Path, *, signing_key: bytes,
                 repository: str, plan_id: str, _initializing=False):
        _private_directory(directory)
        super().__init__(directory, signing_key=signing_key,
                         repository=repository, plan_id=plan_id)
        self.db_path = self.path.with_suffix(".sqlite3")
        if not _initializing:
            with self._db() as db:
                self._row(db)
                if db.execute("PRAGMA user_version").fetchone() != (2,):
                    raise ClosureError("CANONICAL_PLAN_SCHEMA_UNSUPPORTED")
                db.execute("SELECT task_id FROM task_attempts LIMIT 1")

    @contextmanager
    def _db(self):
        _private_directory(self.directory)
        _private_file(self.db_path)
        with closing(sqlite3.connect(self.db_path.as_uri()+"?mode=rw", uri=True, timeout=5)) as db:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db

    def _row(self, db):
        row = db.execute("SELECT identity,snapshot,closure FROM plan WHERE id=1").fetchone()
        if row is None or row[0] != self.identity:
            raise ClosureError("CANONICAL_PLAN_IDENTITY_MISMATCH")
        return row

    def read_snapshot(self):
        with self._db() as db:
            return _snapshot(json.loads(self._row(db)[1]))

    def update_snapshot(self, snapshot: PlanSnapshot, *, expected: PlanSnapshot | None = None):
        """Trusted lifecycle update. Once a closure attempt exists, freeze it."""
        with self.locked(), self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            _, old, closure = self._row(db)
            previous = _snapshot(json.loads(old))
            if expected is not None and previous != expected:
                raise ClosureError("STALE_PLAN_SNAPSHOT")
            if db.execute("SELECT 1 FROM task_attempts WHERE state!='COMPLETED' LIMIT 1").fetchone():
                raise ClosureError("UNRESOLVED_TASK_ATTEMPT")
            if (closure is not None or previous.workflow_state == "PLAN_DONE"
                    or snapshot.plan_id != previous.plan_id
                    or snapshot.workflow_state not in {"ACTIVE","PLAN_READY_FOR_APPROVAL"}):
                raise ClosureError("CANONICAL_PLAN_UPDATE_BLOCKED")
            db.execute("UPDATE plan SET snapshot=? WHERE id=1", (canonicalize(json.loads(json.dumps(asdict(snapshot)))),))

    def begin_task_completion(self, *, task_id: str, session_id: str):
        if not isinstance(session_id,str) or not session_id:
            raise ClosureError("INVALID_TASK_SESSION")
        with self.locked(), self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            _, raw, closure = self._row(db)
            snapshot = _snapshot(json.loads(raw))
            if (closure is not None or snapshot.workflow_state != "ACTIVE"
                    or task_id not in snapshot.required_tasks
                    or task_id in snapshot.completed_tasks
                    or db.execute("SELECT 1 FROM task_attempts WHERE state!='COMPLETED' LIMIT 1").fetchone()):
                raise ClosureError("TASK_ATTEMPT_BLOCKED")
            try:
                db.execute("INSERT INTO task_attempts VALUES (?,?,'IN_FLIGHT',NULL)",
                           (task_id,session_id))
            except sqlite3.IntegrityError as exc:
                raise ClosureError("TASK_ATTEMPT_ALREADY_EXISTS") from exc

    def mark_task_uncertain(self, *, task_id: str, session_id: str):
        with self.locked(), self._db() as db:
            db.execute("UPDATE task_attempts SET state='UNCERTAIN' WHERE task_id=? AND session_id=? AND state='IN_FLIGHT'",
                       (task_id,session_id))

    def record_verified_task(self, *, task_id: str, session_id: str, completion: dict):
        """Trusted controller only: record a commit it just verified/published.

        Never expose as worker IPC. A committed Git ref without this durable
        transition remains incomplete; no speculative recovery of completion.
        """
        if (set(completion) != {"commit", "tree", "evidenceDigest"}
                or any(not isinstance(v, str) or not v for v in completion.values())
                or any(not re.fullmatch(r"[0-9a-f]{40}",completion[k]) for k in ("commit","tree"))
                or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}",completion["evidenceDigest"])):
            raise ClosureError("INVALID_COMPLETION_EVIDENCE")
        with self.locked(), self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            _, raw, closure = self._row(db)
            previous = _snapshot(json.loads(raw))
            if (closure is not None or previous.workflow_state != "ACTIVE"
                    or task_id not in previous.required_tasks
                    or task_id in previous.completed_tasks):
                raise ClosureError("TASK_COMPLETION_BLOCKED")
            entry = db.execute("SELECT session_id,state FROM task_attempts WHERE task_id=?",(task_id,)).fetchone()
            if entry != (session_id,"IN_FLIGHT"):
                raise ClosureError("TASK_COMPLETION_NOT_PREPARED")
            db.execute("UPDATE task_attempts SET state='COMPLETED',evidence=? WHERE task_id=?",
                       (canonicalize(completion),task_id))
            completed = tuple(sorted((*previous.completed_tasks, task_id)))
            evidence = tuple(sorted((*previous.evidence, digest_json({
                "schema":"workflow.verified-task-completion.v1",
                "taskId":task_id, **completion,
            }))))
            # Completing every task is necessary but not sufficient for
            # plan-wide validation. Keep ACTIVE until separately verified.
            updated = replace(previous, completed_tasks=completed, evidence=evidence,
                              validation_summary={"status":"PENDING"})
            db.execute("UPDATE plan SET snapshot=? WHERE id=1",
                       (canonicalize(json.loads(json.dumps(asdict(updated)))),))
            return updated

    def source(self, repo_root: Path, repository: str, plan_id: str):
        return ClosureSource(repo_root, repository, plan_id, self.read_snapshot)

    def load(self):
        with self._db() as db:
            raw = self._row(db)[2]
        if raw is None:
            return None
        envelope = json.loads(raw)
        mac = envelope.pop("mac", None)
        if (not isinstance(mac, str) or not hmac.compare_digest(mac, self._mac(envelope))
                or envelope.get("identity") != self.identity
                or envelope.get("schema") != "workflow.closure-journal.v1"):
            raise ClosureError("CLOSURE_INTEGRITY_FAILED")
        return envelope

    def _write(self, record):
        if record.get("identity") != self.identity:
            raise ClosureError("CLOSURE_IDENTITY_MISMATCH")
        raw = canonicalize({**record, "mac": self._mac(record)})
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            _, snapshot_json, old = self._row(db)
            if record["state"] == "PLAN_DONE":
                previous = json.loads(old) if old is not None else {}
                old_mac = previous.pop("mac", None)
                if (not isinstance(old_mac,str) or not hmac.compare_digest(old_mac,self._mac(previous))
                        or previous.get("state") != "CONSUMPTION_IN_FLIGHT"
                        or any(previous.get(k) != record.get(k) for k in
                               ("requestId","executionId","actionDigest","audience"))
                        or not record.get("grantDigest")):
                    raise ClosureError("CLOSURE_NOT_VERIFIED")
                snapshot = json.loads(snapshot_json)
                if snapshot["workflow_state"] != "PLAN_READY_FOR_APPROVAL":
                    raise ClosureError("PLAN_NOT_READY")
                snapshot["workflow_state"] = "PLAN_DONE"
                db.execute("UPDATE plan SET snapshot=?,closure=? WHERE id=1",
                           (canonicalize(snapshot), raw))
            else:
                if old is not None and json.loads(old).get("state") == "PLAN_DONE":
                    raise ClosureError("PLAN_ALREADY_CLOSED")
                db.execute("UPDATE plan SET closure=? WHERE id=1", (raw,))
