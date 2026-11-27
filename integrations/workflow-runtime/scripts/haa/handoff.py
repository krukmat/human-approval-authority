"""Trusted controller-only implementer handoff, with no new HAA authority.

Model identities are not authorities. A switch of implementer inside the
same protected task/session and worker UID may reuse its live lease. A
different worker UID, base, policy/card or session requires a fresh session.
No worker-callable method or cross-identity transfer is exposed.
"""
from dataclasses import dataclass
from scripts.haa.live_verify import _git


class HandoffError(RuntimeError):
    pass


@dataclass(frozen=True)
class HandoffPin:
    repository: str
    session_id: str
    worker_uid: int
    card_sha256: str
    policy_digest: str
    branch: str
    base_commit_sha: str


def live_handoff_pin(authority, *, worker_uid):
    if type(worker_uid) is not int or worker_uid<=0:
        raise HandoffError("INVALID_HANDOFF_WORKER")
    with authority._lock:
        authority._require_started()
        authority._check("test")
        task=authority.scope.task
        lease=authority.leases.load(authority.scope.lease_id)
        if task.policy_pin is None or task.card_sha256 is None or not lease.grant_digest:
            raise HandoffError("HANDOFF_VERIFIED_AUTHORITY_REQUIRED")
        branch=_git(task.repo_root.resolve(),"symbolic-ref","--quiet","--short","HEAD")
        head=_git(task.repo_root.resolve(),"rev-parse","--verify","HEAD")
        if (head!=lease.base_commit_sha or branch!=lease.branch
                or task.session_id!=lease.session_id or task.repository!=lease.repository):
            raise HandoffError("HANDOFF_LIVE_SCOPE_CHANGED")
        return HandoffPin(task.repository,task.session_id,worker_uid,task.card_sha256,
                          task.policy_pin.digest(),branch,head)


def validate_handoff(authority, requested, *, worker_uid):
    if not isinstance(requested,HandoffPin) or requested.worker_uid!=worker_uid:
        raise HandoffError("HANDOFF_NEW_WORKER_REQUIRES_AUTHORITY")
    if live_handoff_pin(authority,worker_uid=worker_uid)!=requested:
        raise HandoffError("HANDOFF_SCOPE_CHANGED")
    return "SAME_LIVE_AUTHORITY"
