"""Immutable, bounded replacement proposals and verification-bound publication.

Trusted executor only. No create/delete, arbitrary commands, remote writes or
implicit expansion of workflow.task.start.v1 authority. A proposal is not
authority. The canonical plan journal must wrap commit(); any failure after
the first filesystem mutation is uncertain and requires owner reconciliation.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
import tempfile

from scripts.haa.contracts import digest_json
from scripts.haa.lease_guard import _path_allowed
from scripts.haa.protected_commit import (
    CandidateTree, CommitError, ProtectedCommit, VerificationResult,
)
from scripts.haa.protected_broker import MAX_CONTENT, _replace_existing

MAX_FILES = 32
MAX_BATCH_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Replacement:
    path: str
    before: str
    content: str


@dataclass(frozen=True)
class BatchProposal:
    changes: tuple[Replacement, ...]

    @property
    def paths(self):
        return tuple(c.path for c in self.changes)


def parse_batch(changes):
    if not isinstance(changes, list) or not 1 <= len(changes) <= MAX_FILES:
        raise CommitError("INVALID_BATCH_SIZE")
    result = []
    total = 0
    aliases = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "before_sha256", "content"}:
            raise CommitError("INVALID_REPLACEMENT_FIELDS")
        path, before, content = (change[k] for k in ("path", "before_sha256", "content"))
        # Restrict the portable batch format to unambiguous ASCII filenames.
        # Case-fold collisions are denied for case-insensitive macOS volumes.
        if (not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,512}", path)
                or any(p in {"", ".", "..", ".git", ".agent"} or p.lower() in {".git", ".agent"}
                       for p in path.split("/")) or path.lower() in aliases):
            raise CommitError("INVALID_OR_DUPLICATE_BATCH_PATH")
        if not isinstance(before, str) or not re.fullmatch(r"[0-9a-f]{64}", before):
            raise CommitError("INVALID_BATCH_PREIMAGE")
        if not isinstance(content, str):
            raise CommitError("INVALID_BATCH_CONTENT")
        try:
            raw = content.encode("utf-8")
        except UnicodeError as exc:
            raise CommitError("INVALID_BATCH_CONTENT") from exc
        total += len(raw)
        if len(raw) > MAX_CONTENT or total > MAX_BATCH_BYTES:
            raise CommitError("BATCH_TOO_LARGE")
        if sha256(raw).hexdigest() == before:
            raise CommitError("NO_REPLACEMENT_CHANGE")
        aliases.add(path.lower())
        result.append(Replacement(path, before, content))
    return BatchProposal(tuple(sorted(result, key=lambda c: c.path)))


class BatchCommit(ProtectedCommit):
    """Stage exact Git objects first; verify before any working tree writes."""

    def __init__(self, authority, *, state, verifier, proposal):
        super().__init__(authority, state=state, verifier=verifier)
        if not isinstance(proposal, BatchProposal):
            raise CommitError("BROKER_BATCH_REQUIRED")
        self.proposal = parse_batch([{"path": c.path, "before_sha256": c.before,
                                     "content": c.content} for c in proposal.changes])
        self._attempted = False

    def _prepare_batch(self, paths, commands):
        if paths != self.proposal.paths:
            raise CommitError("BATCH_PATHS_MISMATCH")
        parent = self._sha("rev-parse", "--verify", "HEAD")
        branch = self._git("symbolic-ref", "--quiet", "HEAD").decode().strip()
        if not branch.startswith("refs/heads/") or branch == "refs/heads/main":
            raise CommitError("PROTECTED_BRANCH_REQUIRED")
        if self._sha("write-tree") != self._sha("rev-parse", parent+"^{tree}"):
            raise CommitError("PREEXISTING_STAGED_CHANGES")
        tracked = self._tracked(parent)
        lease = self.authority.leases.load(self.authority.scope.lease_id)
        # Bind to initial task HEAD, not arbitrary descendants.
        if parent != lease.base_commit_sha:
            raise CommitError("BATCH_BASE_CHANGED")
        task = self.authority.scope.task
        pinned = {str(task.card_path.resolve().relative_to(self.root))}
        pinned.update(path for path, _ in task.policy_pin.sources)
        validated = []
        for c in self.proposal.changes:
            if c.path in pinned or c.path not in tracked or not _path_allowed(self.root, c.path, lease.allowed_paths):
                raise CommitError("BATCH_PATH_OUTSIDE_TRACKED_SCOPE")
            self.authority.existing.check_write(c.path)
            mode, kind, oid = tracked[c.path]
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise CommitError("UNSUPPORTED_BATCH_OBJECT")
            original = self._read(c.path)
            # No dirty preimages, filters or worker-supplied mode changes.
            if (sha256(original).hexdigest() != c.before
                    or self._sha("hash-object", "--no-filters", "--stdin", data=original) != oid):
                raise CommitError("STALE_OR_DIRTY_BATCH_PREIMAGE")
            try:
                original.decode("utf-8")
            except UnicodeError as exc:
                raise CommitError("NON_TEXT_BATCH_PREIMAGE") from exc
            validated.append((c, mode))
        # All paths and preimages validated before creating candidate objects.
        with tempfile.TemporaryDirectory(prefix="batch-index-", dir=self.state) as tmp:
            from pathlib import Path
            index = Path(tmp) / "index"
            self._git("read-tree", parent, index=index)
            for c, mode in validated:
                oid = self._sha("hash-object", "-w", "--no-filters", "--stdin", data=c.content.encode("utf-8"))
                self._git("update-index", "--cacheinfo", mode, oid, c.path, index=index)
            tree = self._sha("write-tree", index=index)
        return CandidateTree(parent, branch, tree, paths, task.session_id,
                             digest_json([list(c) for c in commands]))

    def commit(self, paths):
        with self.authority._lock, self._lock:
            if self._attempted:
                raise CommitError("BATCH_ALREADY_ATTEMPTED")
            self._attempted = True
            self.authority._require_started()
            self.authority._check("edit", paths)
            self.authority._check("commit", paths)
            self.authority._check("test")
            commands = self._commands()
            candidate = self._prepare_batch(paths, commands)
            result = self.verifier.verify(candidate, commands)
            if (not isinstance(result, VerificationResult)
                    or any(type(code) is not int for code in result.exit_codes)
                    or (result.tree, result.session, result.commands_digest) !=
                       (candidate.tree, candidate.session, candidate.commands_digest)
                    or result.exit_codes != (0,) * len(commands)
                    or not isinstance(result.evidence_digest, str)
                    or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}", result.evidence_digest)):
                raise CommitError("VERIFICATION_NOT_BOUND_OR_FAILED")
            self.authority._check("edit", paths)
            self.authority._check("commit", paths)
            self.authority._check("test")
            if self._prepare_batch(paths, self._commands()) != candidate:
                raise CommitError("BATCH_CHANGED_DURING_VERIFICATION")
            commit = self._sha("commit-tree", candidate.tree, "-p", candidate.parent,
                               "-m", "HAA bounded batch change [skip ci]")
            # The protected plan journal records an in-flight task before this
            # method is called. Checkout mutation is NOT a filesystem-wide
            # atomic transaction. A crash leaves uncertain state, no auto retry.
            for c in self.proposal.changes:
                self.authority._check("edit", (c.path,))
                _replace_existing(self.root, c.path, c.before, c.content)
            self.authority._check("commit", paths)
            self.authority._check("test")
            for c in self.proposal.changes:
                if self._read(c.path) != c.content.encode("utf-8"):
                    raise CommitError("BATCH_CHECKOUT_DRIFT")
            if self._sha("write-tree") != self._sha("rev-parse", candidate.parent+"^{tree}"):
                raise CommitError("PREEXISTING_STAGED_CHANGES")
            self._git("update-ref", candidate.branch, commit, candidate.parent)
            self._git("read-tree", commit)
            if self._sha("write-tree") != candidate.tree:
                raise CommitError("CHECKOUT_RECONCILIATION_FAILED")
            return {"status": "COMMITTED_LOCAL", "commit": commit, "tree": candidate.tree,
                    "evidenceDigest": result.evidence_digest, "checkoutReconciliationRequired": False}
