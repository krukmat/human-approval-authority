"""Trusted plan initialization/projection and independent closure entrypoint.

The owner supplies an exact committed plan manifest through a protected
deployment channel. Markdown completion boxes are never imported as
authority. This module has no worker-facing RPC or automatic activation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
from threading import RLock

from scripts.haa.contracts import digest_json
from scripts.haa.plan_closure import (
    ClosureError, PlanSnapshot, request_plan_close, finalize_plan_close,
)
from scripts.haa.protected_host import validate_layout
from scripts.haa.protected_plan import ProtectedPlanJournal


@dataclass(frozen=True)
class ApprovedPlan:
    repository: str
    plan_id: str
    branch: str
    base_commit: str
    plan_path: str
    plan_sha256: str
    ledger_path: str
    ledger_sha256: str
    required_tasks: tuple[str, ...]


def _git(root: Path, *argv):
    result = subprocess.run(
        ["/usr/bin/git","-C",str(root),"-c","core.hooksPath=/dev/null",
         "-c","core.fsmonitor=false",*argv],capture_output=True,timeout=15,
        env={"PATH":"/usr/bin:/bin","LANG":"C","HOME":"/var/empty",
             "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
             "GIT_NO_REPLACE_OBJECTS":"1","GIT_TERMINAL_PROMPT":"0"},
        check=False)
    if result.returncode:
        raise ClosureError("PROTECTED_PLAN_GIT_FAILED")
    return result.stdout


def _committed_document(root: Path, commit: str, path: str, expected: str):
    if (not isinstance(path,str) or not path.startswith("docs/") or not path.endswith(".md")
            or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/"))
            or not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected)):
        raise ClosureError("INVALID_PLAN_DOCUMENT_PIN")
    # Object type must be a regular committed document, not a symlink/submodule.
    entries = _git(root,"ls-tree","-z",commit,"--",path).split(b"\0")
    if len(entries) != 2 or not entries[0]:
        raise ClosureError("PLAN_DOCUMENT_MISSING")
    meta, name = entries[0].split(b"\t",1)
    mode, kind, oid = meta.decode("ascii").split()
    if mode not in {"100644","100755"} or kind!="blob" or name.decode()!=path:
        raise ClosureError("INVALID_PLAN_DOCUMENT_OBJECT")
    raw = _git(root,"cat-file","blob",oid)
    if len(raw)>1024*1024 or sha256(raw).hexdigest()!=expected:
        raise ClosureError("PLAN_DOCUMENT_DIGEST_MISMATCH")


def _check_repo(root: Path, approved: ApprovedPlan, *, initial=False):
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",approved.repository)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+",approved.plan_id)
            or not re.fullmatch(r"[0-9a-f]{40}",approved.base_commit)):
        raise ClosureError("INVALID_APPROVED_PLAN")
    if Path(_git(root,"rev-parse","--show-toplevel").decode().strip()).resolve()!=root:
        raise ClosureError("PROTECTED_PLAN_ROOT_MISMATCH")
    origin=_git(root,"remote","get-url","origin").decode().strip()
    if origin not in {f"https://github.com/{approved.repository}",
                      f"https://github.com/{approved.repository}.git",
                      f"git@github.com:{approved.repository}.git",
                      f"ssh://git@github.com/{approved.repository}.git"}:
        raise ClosureError("PROTECTED_PLAN_ORIGIN_MISMATCH")
    if _git(root,"symbolic-ref","--short","HEAD").decode().strip()!=approved.branch:
        raise ClosureError("PROTECTED_PLAN_BRANCH_MISMATCH")
    head=_git(root,"rev-parse","HEAD").decode().strip()
    if initial and head!=approved.base_commit:
        raise ClosureError("PLAN_BASE_HEAD_MISMATCH")
    _git(root,"merge-base","--is-ancestor",approved.base_commit,head)
    return head


def _version(approved: ApprovedPlan):
    return digest_json({
        "repository":approved.repository,"planId":approved.plan_id,
        "branch":approved.branch,"baseCommit":approved.base_commit,
        "planPath":approved.plan_path,"planSha256":approved.plan_sha256,
        "ledgerPath":approved.ledger_path,"ledgerSha256":approved.ledger_sha256,
        "requiredTasks":list(approved.required_tasks),
    })


def initialize_plan(*, layout, approved: ApprovedPlan, directory: Path, signing_key: bytes):
    """Initialize an actual protected plan; explicit trusted manifest only."""
    validate_layout(layout)
    if (not isinstance(directory,Path) or directory.resolve()!=directory
            or not directory.is_relative_to(layout.state)):
        raise ClosureError("PLAN_OUTSIDE_PROTECTED_STATE")
    root=layout.target
    _check_repo(root,approved,initial=True)
    if _git(root,"status","--porcelain","--untracked-files=normal"):
        raise ClosureError("PLAN_BASE_NOT_CLEAN")
    tasks=approved.required_tasks
    if (not isinstance(tasks,tuple) or not tasks
            or any(not isinstance(t,str) or not t.strip() for t in tasks)
            or tuple(sorted(set(tasks)))!=tasks):
        raise ClosureError("INVALID_APPROVED_TASK_SET")
    _committed_document(root,approved.base_commit,approved.plan_path,approved.plan_sha256)
    _committed_document(root,approved.base_commit,approved.ledger_path,approved.ledger_sha256)
    # Deliberately begin ACTIVE with zero completions even if a Markdown
    # ledger contains [x] markers. Existing plans require explicit migration
    # evidence, not an automatic import of completion flags.
    return ProtectedPlanJournal.initialize(directory,signing_key=signing_key,
        repository=approved.repository,snapshot=PlanSnapshot(
            "ACTIVE",approved.plan_id,_version(approved),tasks,(),(),(),
            {"status":"PENDING"},()))


class PlanCloseController:
    """Independent protected plan-close supervisor, after task lease revocation.

    The deployment owns the shared target lock and must prevent other writers.
    The verifier is trusted supervisor code with a separately certified
    execution backend, never a callback chosen by a worker.
    """
    def __init__(self, *, layout, approved: ApprovedPlan, journal: ProtectedPlanJournal,
                 supervisor_lock: RLock, assert_no_active_tasks, verify_plan):
        validate_layout(layout)
        if not isinstance(journal,ProtectedPlanJournal) or not journal.directory.is_relative_to(layout.state):
            raise ClosureError("PROTECTED_PLAN_REQUIRED")
        self.layout=layout
        self.approved=approved
        self.journal=journal
        self.lock=supervisor_lock
        self.assert_no_active_tasks=assert_no_active_tasks
        self.verify_plan=verify_plan

    def _context(self):
        self.assert_no_active_tasks()
        head=_check_repo(self.layout.target,self.approved)
        snapshot=self.journal.read_snapshot()
        if (snapshot.plan_id!=self.approved.plan_id
                or snapshot.plan_version!=_version(self.approved)
                or snapshot.required_tasks!=self.approved.required_tasks
                or self.journal.identity!=digest_json({
                    "repository":self.approved.repository,"planId":self.approved.plan_id})):
            raise ClosureError("APPROVED_PLAN_BINDING_MISMATCH")
        if _git(self.layout.target,"status","--porcelain","--untracked-files=normal"):
            raise ClosureError("CLOSURE_WORKTREE_NOT_CLEAN")
        return head,snapshot

    def mark_ready(self):
        with self.lock:
            head,before=self._context()
            if (before.workflow_state!="ACTIVE" or
                    set(before.required_tasks)!=set(before.completed_tasks)):
                raise ClosureError("PLAN_TASKS_INCOMPLETE")
            result=self.verify_plan(head,before)
            if (not isinstance(result,dict) or set(result)!={"status","head","evidenceDigest"}
                    or result["status"]!="PASS" or result["head"]!=head
                    or not isinstance(result["evidenceDigest"],str)
                    or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}",result["evidenceDigest"])):
                raise ClosureError("PLAN_VALIDATION_FAILED")
            if self._context()!=(head,before):
                raise ClosureError("PLAN_CHANGED_DURING_VALIDATION")
            self.journal.update_snapshot(replace(before,workflow_state="PLAN_READY_FOR_APPROVAL",
                validation_summary=result,
                evidence=tuple(sorted(set((*before.evidence,result["evidenceDigest"]))))),
                expected=before)
            return self.journal.read_snapshot()

    def _source(self):
        head,snapshot=self._context()
        if (snapshot.workflow_state!="PLAN_READY_FOR_APPROVAL"
                or snapshot.validation_summary.get("head")!=head):
            raise ClosureError("PLAN_NOT_READY_OR_VALIDATION_STALE")
        return self.journal.source(self.layout.target,self.approved.repository,self.approved.plan_id)

    def request_close(self,requester):
        with self.lock:
            return request_plan_close(source=self._source(),journal=self.journal,requester=requester)

    def finalize_close(self,executor,pin):
        with self.lock:
            return finalize_plan_close(source=self._source(),journal=self.journal,executor=executor,pin=pin)

    def projection(self):
        """Read-only derived status for a human/ledger renderer; no writeback."""
        with self.lock:
            snapshot=self.journal.read_snapshot()
            record=self.journal.load()
            return {"schema":"workflow.protected-plan-projection.v1",
                "planId":snapshot.plan_id,"planVersion":snapshot.plan_version,
                "state":snapshot.workflow_state,"requiredTasks":list(snapshot.required_tasks),
                "completedTasks":list(snapshot.completed_tasks),
                "validation":snapshot.validation_summary,
                "closureGrantDigest":record.get("grantDigest") if record and
                    record["state"]=="PLAN_DONE" else None}
