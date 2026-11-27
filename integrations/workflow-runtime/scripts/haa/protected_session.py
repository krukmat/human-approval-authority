"""Trusted, single-session service lifecycle for ADR-049.

No owner control is exposed over the worker socket. This module is a
deployment building block, not a daemon installer or production entrypoint.
The host must prove isolated credentials, runtime, target and worker.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
from threading import RLock
from time import monotonic

from scripts.haa.live_verify import bind_trusted_task
from scripts.haa.policy import PolicyPin
from scripts.haa.protected_broker import WorkerBroker
from scripts.haa.protected_host import validate_layout
from scripts.haa.request_checkpoint import reconcile_status
from scripts.haa.runner_authority import (
    RunnerAuthority, RunnerScope, request_bound_task, activate_bound_task,
)
from scripts.haa.volatile_authority import VolatileLeaseStore
from scripts.haa.authority_lease import LeaseError


class SessionError(RuntimeError):
    pass


class ProtectedSession:
    """Fresh in-memory attempt per service generation, no resume from disk.

    Every method except serve_worker belongs to the trusted supervisor.
    Do not expose these methods as worker IPC operations.
    """
    def __init__(self, *, layout, task, card_sha256, authoritative_rri,
                 checkpoints, leases, requester, executor, pin, existing_boundary, policy_pin=None):
        validate_layout(layout)
        if not isinstance(leases, VolatileLeaseStore):
            raise SessionError("VOLATILE_AUTHORITY_REQUIRED")
        if not checkpoints.authenticated:
            raise SessionError("AUTHENTICATED_CHECKPOINT_REQUIRED")
        if task.repo_root.resolve() != layout.target:
            raise SessionError("PROTECTED_TARGET_REQUIRED")
        if not checkpoints.directory.resolve().is_relative_to(layout.state):
            raise SessionError("CHECKPOINT_OUTSIDE_PROTECTED_STATE")
        if not leases.journal.directory.is_relative_to(layout.state):
            raise SessionError("JOURNAL_OUTSIDE_PROTECTED_STATE")
        # Candidate privileged workflow deliberately supports only the
        # exact-grant high-band path. No new low-band exception is inferred.
        if not isinstance(policy_pin, PolicyPin) or policy_pin.requires_haa is not True:
            raise SessionError("EXPLICIT_POLICY_AUTHORITY_REQUIRED")
        self.task = bind_trusted_task(task, card_sha256=card_sha256,
                                      authoritative_rri=authoritative_rri, policy_pin=policy_pin)
        self.layout = layout
        self.checkpoints = checkpoints
        self.leases = leases
        self.requester = requester
        self.executor = executor
        self.pin = pin
        self.existing_boundary = existing_boundary
        self._lock = RLock()
        self._attempted = False
        self._activation_attempted = False
        self._attempt = None
        self._authority = None
        self._closed = False
        self._worker_window_used = False
        self._accepted_edit = None

    def request(self):
        with self._lock:
            if self._closed or self._attempted:
                raise SessionError("SESSION_REQUEST_ALREADY_ATTEMPTED")
            self._attempted = True
            self._attempt = request_bound_task(task=self.task, requester=self.requester,
                                               checkpoints=self.checkpoints)
            return self._attempt.status

    def poll(self):
        with self._lock:
            if self._closed or self._attempt is None or self._activation_attempted:
                raise SessionError("SESSION_NOT_WAITING")
            self._attempt = reconcile_status(self.requester, self.checkpoints,
                                             self._attempt.attempt_id)
            return self._attempt.status

    def activate(self):
        with self._lock:
            if (self._closed or self._activation_attempted or self._attempt is None
                    or self._attempt.status != "APPROVED_NOT_CONSUMED"):
                raise SessionError("SESSION_NOT_APPROVED")
            self._activation_attempted = True
            lease = activate_bound_task(task=self.task, executor=self.executor,
                                        checkpoints=self.checkpoints, leases=self.leases,
                                        attempt_id=self._attempt.attempt_id, pin=self.pin)
            try:
                authority = RunnerAuthority(scope=RunnerScope(self.task, lease.lease_id),
                                            leases=self.leases, existing_boundary=self.existing_boundary)
                authority.preflight()
                self._authority = authority
            except BaseException:
                # Admission cannot be repeated after any post-consume failure.
                try:
                    self.leases.revoke(lease.lease_id)
                except LeaseError:
                    pass
                raise

    def authorize_handoff(self, requested):
        """Owner channel only, before a worker proposal window is opened."""
        from scripts.haa.handoff import validate_handoff
        with self._lock:
            if self._closed or self._authority is None or self._worker_window_used:
                raise SessionError("HANDOFF_WINDOW_UNAVAILABLE")
            try:
                return validate_handoff(self._authority, requested, worker_uid=self.layout.worker_uid)
            except BaseException:
                # A scope/identity mismatch must never leave the old session usable.
                self.close()
                raise

    def serve_worker(self, listener: socket.socket, *, duration_seconds: int = 60):
        """Serve an already protected Unix listener, for a bounded window.

        Socket provisioning/permissions are an admin deployment concern;
        validate them before use. No subprocess is started by the executor.
        """
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 1800:
            raise SessionError("INVALID_SERVE_DURATION")
        with self._lock:
            if self._closed or self._authority is None:
                raise SessionError("SESSION_NOT_ACTIVE")
            if listener.family != socket.AF_UNIX or listener.type != socket.SOCK_STREAM:
                raise SessionError("UNIX_LISTENER_REQUIRED")
            path = Path(listener.getsockname())
            st = path.lstat()
            parent = path.parent.lstat()
            if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o007 or parent.st_uid != os.geteuid()
                    or parent.st_mode & 0o022 or path.parent.resolve() != path.parent):
                raise SessionError("UNSAFE_SOCKET_LOCATION")
            if self._worker_window_used:
                raise SessionError("WORKER_WINDOW_ALREADY_USED")
            self._worker_window_used = True
            broker = WorkerBroker(self._authority, worker_uid=self.layout.worker_uid)
            until = monotonic() + duration_seconds
            listener.settimeout(1)
            try:
                while monotonic() < until:
                    # Stop as soon as live authority expires or is revoked.
                    self.leases.load(self._authority.scope.lease_id)
                    try:
                        conn, _ = listener.accept()
                    except TimeoutError:
                        continue
                    with conn:
                        broker.handle(conn)
                    if broker._accepted is not None:
                        break
                self._accepted_edit = broker.seal()
                if self._accepted_edit is None:
                    raise SessionError("NO_ACCEPTED_WORKER_PROPOSAL")
            except BaseException:
                self.close()
                raise
            finally:
                listener.close()
            # Successful end of the worker window is not task completion.
            # Only the supervisor can verify/publish while the lease is live.

    def complete_task(self, *, plan, verifier, paths: tuple[str,...]):
        from scripts.haa.protected_commit import ProtectedCommit
        from scripts.haa.batch_commit import BatchProposal, BatchCommit
        from scripts.haa.protected_workflow import ProtectedWorkflow
        with self._lock:
            if self._closed or self._authority is None or self._accepted_edit is None:
                raise SessionError("ACCEPTED_WORKER_PROPOSAL_REQUIRED")
            batch = isinstance(self._accepted_edit, BatchProposal)
            expected_paths = self._accepted_edit.paths if batch else (self._accepted_edit[0],)
            if paths != expected_paths:
                self.close()
                raise SessionError("COMMIT_PATH_NOT_BROKER_ACCEPTED")
            if not plan.directory.resolve().is_relative_to(self.layout.state):
                raise SessionError("PLAN_OUTSIDE_PROTECTED_STATE")
            try:
                adapter = (BatchCommit(self._authority, state=self.layout.state, verifier=verifier,
                                       proposal=self._accepted_edit) if batch else
                           ProtectedCommit(self._authority, state=self.layout.state, verifier=verifier,
                                           accepted_edit=self._accepted_edit))
                workflow = ProtectedWorkflow(commit_adapter=adapter, plan=plan)
                return workflow.complete_task(paths)
            finally:
                self.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self._authority is not None:
                    self._authority.close()
            finally:
                self.leases.close()
