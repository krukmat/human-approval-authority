"""S3.7c/d: connect verified local task effects to canonical plan lifecycle.

No worker-controlled PASS, task closure or PLAN_DONE. A trusted supervisor
must serialize ALL protected target mutation and workflow operations.
No automatically resumed side effect after failure.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from threading import RLock

from scripts.haa.contracts import digest_json
from scripts.haa.live_verify import checked_bound_card
from scripts.haa.plan_closure import (
    ClosureError, request_plan_close, finalize_plan_close,
)
from scripts.haa.protected_commit import ProtectedCommit
from scripts.haa.protected_plan import ProtectedPlanJournal


class ProtectedWorkflow:
    def __init__(self, *, commit_adapter: ProtectedCommit, plan: ProtectedPlanJournal):
        if not isinstance(plan, ProtectedPlanJournal):
            raise ClosureError("PROTECTED_PLAN_REQUIRED")
        if not isinstance(commit_adapter, ProtectedCommit):
            raise ClosureError("PROTECTED_COMMIT_REQUIRED")
        self.commit_adapter = commit_adapter
        self.plan = plan
        self._lock = RLock()
        self._failed = False
        self._completed = False
        self._closed = False

    def _context(self):
        if self._failed or self._closed:
            raise ClosureError("WORKFLOW_STOPPED")
        authority = self.commit_adapter.authority
        task = authority.scope.task
        card = checked_bound_card(task, task.repo_root.resolve(), required=True)
        snapshot = self.plan.read_snapshot()
        if (not card.plan or Path(card.plan).stem != snapshot.plan_id
                or self.plan.identity != digest_json({
                    "repository":task.repository, "planId":snapshot.plan_id})):
            raise ClosureError("PLAN_TASK_BINDING_MISMATCH")
        return authority, task, card, snapshot

    def complete_task(self, paths: tuple[str,...]):
        """Publish one verified commit and persist its task disposition.

        If recording fails after Git publication, stop. The commit may exist
        but the task is not DONE; reconcile by explicit operator inspection.
        """
        with self._lock, self.commit_adapter.authority._lock:
            authority, task, card, snapshot = self._context()
            if (self._completed or snapshot.workflow_state != "ACTIVE"
                    or card.task_id not in snapshot.required_tasks
                    or card.task_id in snapshot.completed_tasks):
                raise ClosureError("TASK_NOT_OPEN")
            self.plan.begin_task_completion(task_id=card.task_id,session_id=task.session_id)
            try:
                result = self.commit_adapter.commit(paths)
                if result["status"] != "COMMITTED_LOCAL":
                    raise ClosureError("COMMIT_NOT_VERIFIED")
                if self.commit_adapter._sha("rev-parse","HEAD") != result["commit"]:
                    raise ClosureError("COMMIT_HEAD_DRIFT")
                self.plan.record_verified_task(task_id=card.task_id, session_id=task.session_id, completion={
                    key:result[key] for key in ("commit","tree","evidenceDigest")})
                self._completed = True
                return result
            except BaseException:
                self._failed = True
                self.plan.mark_task_uncertain(task_id=card.task_id,session_id=task.session_id)
                raise
            finally:
                # No further task operations, even if the canonical record
                # failed after the Git ref advanced.
                authority.close()

    def mark_ready(self, *, validation):
        """Consume a deployment-owned validation function, not an IPC field.

        Validation must inspect the exact current protected HEAD and plan,
        with pinned plan-wide acceptance criteria and trustworthy provenance.
        This callback is a supervisor dependency, NOT a security boundary.
        """
        with self._lock, self.commit_adapter.authority._lock:
            _, task, _, before = self._context()
            if (before.workflow_state != "ACTIVE" or not before.required_tasks
                    or set(before.required_tasks) != set(before.completed_tasks)):
                raise ClosureError("REQUIRED_TASKS_NOT_COMPLETED")
            root = task.repo_root.resolve()
            head = self.commit_adapter._sha("rev-parse","HEAD")
            if self.commit_adapter._git("status","--porcelain","--untracked-files=normal"):
                raise ClosureError("CLOSURE_WORKTREE_NOT_CLEAN")
            result = validation(head, before)
            if (not isinstance(result,dict) or set(result) != {"status","head","evidenceDigest"}
                    or result["status"] != "PASS" or result["head"] != head
                    or not isinstance(result["evidenceDigest"],str)
                    or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}",result["evidenceDigest"])):
                raise ClosureError("PLAN_VALIDATION_FAILED")
            if (self.commit_adapter._sha("rev-parse","HEAD") != head
                    or self.plan.read_snapshot() != before
                    or self.commit_adapter._git("status","--porcelain","--untracked-files=normal")):
                raise ClosureError("PLAN_CHANGED_DURING_VALIDATION")
            self.plan.update_snapshot(replace(before,workflow_state="PLAN_READY_FOR_APPROVAL",
                validation_summary=result, evidence=tuple(sorted(set(
                    (*before.evidence,result["evidenceDigest"]))))), expected=before)
            return self.plan.read_snapshot()

    def request_close(self, requester):
        with self._lock, self.commit_adapter.authority._lock:
            _, task, _, snapshot = self._context()
            if (snapshot.workflow_state != "PLAN_READY_FOR_APPROVAL"
                    or snapshot.validation_summary.get("head") != self.commit_adapter._sha("rev-parse","HEAD")):
                raise ClosureError("PLAN_NOT_READY_OR_VALIDATION_STALE")
            return request_plan_close(source=self.plan.source(task.repo_root,task.repository,
                snapshot.plan_id),journal=self.plan,requester=requester)

    def finalize_close(self, executor, pin):
        with self._lock, self.commit_adapter.authority._lock:
            _, task, _, snapshot = self._context()
            if snapshot.validation_summary.get("head") != self.commit_adapter._sha("rev-parse","HEAD"):
                raise ClosureError("PLAN_VALIDATION_STALE")
            result=finalize_plan_close(source=self.plan.source(task.repo_root,task.repository,
                snapshot.plan_id),journal=self.plan,executor=executor,pin=pin)
            self._closed=True
            return result
