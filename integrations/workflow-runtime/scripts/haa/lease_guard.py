"""W3.T3.6: fail-closed escalation guard for HMAC-sealed AuthorityLeases.

Purely advisory for future trusted runners: ALLOW means the scoped lease
passes this guard, not that a side effect has been performed. The caller
must enforce this at every operation boundary in W3.T3.8.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess

from scripts.haa.authority_lease import AuthorityLease, LeaseError, LeaseStore
from scripts.haa.contracts import build_task_scope, digest_json
from scripts.haa.live_verify import (
    LiveAuthorityError, TrustedTask, _git, checked_bound_card,
)

_ROUTINE = frozenset({"edit", "test", "review", "commit"})
_SEPARATE_PROFILE = {
    "merge": "git.merge.v1",
    "plan_close": "workflow.plan.close.v1",
}
_OTHER_PROTECTED = frozenset({
    "push", "create_pr", "deploy", "release", "secrets", "delete",
    "overwrite", "migration", "external_call", "privileged_operation",
})


@dataclass(frozen=True)
class LeaseDecision:
    outcome: str
    reason: str
    action_profile: str | None = None


def _reapproval(store: LeaseStore, lease: AuthorityLease, reason: str) -> LeaseDecision:
    # Never return REQUIRE_HAA after an invalidation unless revocation
    # itself durably succeeds. If storage fails, caller receives BLOCK.
    store.revoke(lease.lease_id)
    return LeaseDecision("REQUIRE_HAA", reason, "workflow.task.start.v1")


def _origin_matches(origin: str, repository: str) -> bool:
    return origin in {
        f"https://github.com/{repository}",
        f"https://github.com/{repository}.git",
        f"git@github.com:{repository}.git",
        f"ssh://git@github.com/{repository}.git",
    }


def _path_allowed(root: Path, relative: str, allowed: tuple[str, ...]) -> bool:
    if (
        not isinstance(relative, str)
        or not relative or relative.startswith("/") or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or relative.startswith(".git/") or relative == ".git"
        or relative.startswith(".agent/") or relative == ".agent"
    ):
        return False
    candidate = root / relative
    if candidate.is_symlink():
        return False
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
        # Refuse symlinks at any ancestor: a lexical match to allowedPaths
        # cannot authorize a different resolved target inside this repo.
        if resolved != candidate.absolute():
            return False
    except (ValueError, OSError):
        return False
    return any(fnmatchcase(relative, pattern) for pattern in allowed)


def evaluate_lease_operation(
    *, store: LeaseStore, lease_id: str, trusted_task: TrustedTask,
    operation: str, touched_paths: tuple[str, ...] = (),
    now: datetime | None = None,
) -> LeaseDecision:
    """Check a persisted lease against current Git/card immediately before use.

    Any path submitted by an agent must still pass the existing local-agent
    boundary. This helper is not an alternative filesystem sandbox.
    """
    if operation in _SEPARATE_PROFILE:
        return LeaseDecision("REQUIRE_HAA", "SEPARATE_EXACT_ACTION_REQUIRED", _SEPARATE_PROFILE[operation])
    if operation in _OTHER_PROTECTED:
        return LeaseDecision("BLOCK", "UNSUPPORTED_PRIVILEGED_ACTION")
    if operation not in _ROUTINE:
        return LeaseDecision("BLOCK", "UNKNOWN_OPERATION")
    if operation in {"edit", "commit"} and not touched_paths:
        return LeaseDecision("BLOCK", "AFFECTED_PATHS_REQUIRED")
    if not isinstance(touched_paths, tuple):
        return LeaseDecision("BLOCK", "INVALID_AFFECTED_PATHS")

    try:
        lease = store.load(lease_id)
        if lease.status != "ACTIVE":
            return LeaseDecision("REQUIRE_HAA", "LEASE_REVOKED", "workflow.task.start.v1")
        clock = now or datetime.now(UTC)
        if clock.tzinfo is None:
            return LeaseDecision("BLOCK", "INVALID_CLOCK")
        if clock.astimezone(UTC) < datetime.fromisoformat(lease.issued_at):
            return _reapproval(store, lease, "LEASE_NOT_YET_VALID")
        if clock.astimezone(UTC) >= datetime.fromisoformat(lease.expires_at):
            return _reapproval(store, lease, "LEASE_EXPIRED")

        if operation not in lease.capabilities:
            return _reapproval(store, lease, "CAPABILITY_ESCALATION")

        root = trusted_task.repo_root.resolve()
        if not root.is_dir() or Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            return LeaseDecision("BLOCK", "INVALID_REPOSITORY_ROOT")
        if not _origin_matches(_git(root, "remote", "get-url", "origin"), lease.repository):
            return _reapproval(store, lease, "REPOSITORY_CHANGED")
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if branch != lease.branch:
            return _reapproval(store, lease, "BRANCH_CHANGED")
        head = _git(root, "rev-parse", "--verify", "HEAD")
        if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
            return LeaseDecision("BLOCK", "INVALID_GIT_HEAD")
        # A commit produced during the approved task can advance HEAD, but
        # rewriting/changing history outside the approved base is escalation.
        ancestry = subprocess.run(
            ["/usr/bin/git", "-C", str(root), "-c", "core.hooksPath=/dev/null",
             "-c", "core.fsmonitor=false", "merge-base", "--is-ancestor", lease.base_commit_sha, head],
            env={"PATH":"/usr/bin:/bin","HOME":"/var/empty","LANG":"C",
                 "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                 "GIT_NO_REPLACE_OBJECTS":"1","GIT_TERMINAL_PROMPT":"0"},
            capture_output=True, timeout=10, check=False,
        )
        if ancestry.returncode != 0:
            return _reapproval(store, lease, "GIT_HISTORY_ESCALATION")

        try:
            card = checked_bound_card(trusted_task, root)
        except LiveAuthorityError:
            if trusted_task.policy_pin is not None:
                return _reapproval(store, lease, "TRUSTED_POLICY_OR_CARD_CHANGED")
            raise
        if (
            card.task_id != lease.task_id or Path(card.plan or "").stem != lease.plan_id
            or trusted_task.session_id != lease.session_id
            or trusted_task.repository != lease.repository
            or not isinstance(card.rri, int) or isinstance(card.rri, bool)
            or card.rri != lease.rri
        ):
            return _reapproval(store, lease, "TASK_OR_RRI_CHANGED")
        normalized = build_task_scope(
            repository=lease.repository, plan_id=lease.plan_id,
            task_id=card.task_id, session_id=trusted_task.session_id,
            branch=branch, base_commit_sha=lease.base_commit_sha,
            allowed_paths=card.allowed_paths,
            capabilities=trusted_task.capabilities,
        )
        if (
            digest_json(normalized) != lease.scope_digest
            or tuple(normalized["allowedPaths"]) != lease.allowed_paths
            or tuple(normalized["capabilities"]) != lease.capabilities
        ):
            return _reapproval(store, lease, "SCOPE_CHANGED")

        if any(not _path_allowed(root, path, lease.allowed_paths)
               for path in touched_paths):
            return _reapproval(store, lease, "PATH_OUTSIDE_SCOPE")
        return LeaseDecision("ALLOW", "VALID_SCOPED_LEASE")
    except (LeaseError, LiveAuthorityError, OSError, ValueError, TypeError,
            subprocess.SubprocessError, KeyError):
        return LeaseDecision("BLOCK", "LEASE_VALIDATION_FAILED")
