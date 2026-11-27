"""S3.7a/b: bounded Git tree preparation and verification-bound local commit.

Trusted service only. No worker IPC publication, checkout, shell, push,
merge or arbitrary command. The protected repository and Git configuration
must be executor-owned; an unprivileged verification backend is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from threading import RLock
from typing import Protocol

from scripts.haa.contracts import digest_json
from scripts.haa.lease_guard import _path_allowed
from scripts.haa.live_verify import checked_bound_card
from scripts.haa.volatile_authority import VolatileLeaseStore

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MAX_FILE = 512 * 1024


class CommitError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateTree:
    parent: str
    branch: str
    tree: str
    paths: tuple[str, ...]
    session: str
    commands_digest: str


@dataclass(frozen=True)
class VerificationResult:
    tree: str
    session: str
    commands_digest: str
    exit_codes: tuple[int, ...]
    evidence_digest: str


class VerificationBackend(Protocol):
    """Trusted deployment-owned backend, not a worker-supplied receipt.

    Must materialize the exact candidate tree in an isolated disposable
    worker domain, execute the pinned commands, and collect actual process
    exit status. Never execute candidate code in the executor.
    """
    def verify(self, candidate: CandidateTree, commands: tuple[tuple[str, ...], ...]) -> VerificationResult: ...


class ProtectedCommit:
    def __init__(self, authority, *, state: Path, verifier: VerificationBackend,
                 accepted_edit: tuple[str,str] | None = None):
        if not isinstance(authority.leases, VolatileLeaseStore):
            raise CommitError("VOLATILE_AUTHORITY_REQUIRED")
        if verifier is None:
            raise CommitError("TRUSTED_VERIFIER_REQUIRED")
        self.authority = authority
        self.root = authority.scope.task.repo_root.resolve()
        self.state = state.resolve()
        st = self.state.stat()
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_mode & 0o077 or self.state.is_relative_to(self.root)):
            raise CommitError("UNSAFE_COMMIT_STATE")
        self.verifier = verifier
        self.accepted_edit = accepted_edit
        self._lock = RLock()

    def _git(self, *args, data=None, index=None):
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(self.state),
            "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0", "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_AUTHOR_NAME": "Workflow protected executor",
            "GIT_AUTHOR_EMAIL": "executor@localhost",
            "GIT_COMMITTER_NAME": "Workflow protected executor",
            "GIT_COMMITTER_EMAIL": "executor@localhost",
        }
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        result = subprocess.run(
            ["/usr/bin/git", "-C", str(self.root), "-c", "core.hooksPath=/dev/null",
             "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false", *args],
            input=data, capture_output=True, env=env, timeout=30, check=False)
        if result.returncode:
            raise CommitError("PROTECTED_GIT_FAILED")
        return result.stdout

    def _sha(self, *args, **kwargs):
        value = self._git(*args, **kwargs).decode("ascii").strip()
        if not _SHA.fullmatch(value):
            raise CommitError("INVALID_GIT_OBJECT")
        return value

    def _tracked(self, parent):
        result = {}
        for line in self._git("ls-tree", "-r", "-z", parent).split(b"\0"):
            if not line:
                continue
            meta, name = line.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split()
            result[name.decode("utf-8")] = (mode, kind, oid)
        return result

    def _read(self, path):
        target = self.root / path
        if target.resolve() != target:
            raise CommitError("UNSAFE_COMMIT_PATH")
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o022):
                raise CommitError("UNSAFE_COMMIT_FILE")
            data = stream.read(_MAX_FILE + 1)
            if len(data) > _MAX_FILE:
                raise CommitError("COMMIT_FILE_TOO_LARGE")
            return data

    def _commands(self):
        card = checked_bound_card(self.authority.scope.task, self.root, required=True)
        commands = tuple(tuple(c.argv) for c in card.verification_commands)
        if not commands:
            raise CommitError("PINNED_TESTS_REQUIRED")
        for argv in commands:
            self.authority.existing.check_command(list(argv))
        return commands

    def _prepare(self, paths, commands):
        if (not isinstance(paths, tuple) or not paths or len(set(paths)) != len(paths)
                or any(not isinstance(p,str) for p in paths)):
            raise CommitError("INVALID_COMMIT_PATHS")
        parent = self._sha("rev-parse", "--verify", "HEAD")
        branch = self._git("symbolic-ref", "--quiet", "HEAD").decode().strip()
        if not branch.startswith("refs/heads/") or branch == "refs/heads/main":
            raise CommitError("PROTECTED_BRANCH_REQUIRED")
        # The canonical index must be clean before a protected publication.
        if self._sha("write-tree") != self._sha("rev-parse",parent+"^{tree}"):
            raise CommitError("PREEXISTING_STAGED_CHANGES")
        tracked = self._tracked(parent)
        lease = self.authority.leases.load(self.authority.scope.lease_id)
        with tempfile.TemporaryDirectory(prefix="index-", dir=self.state) as tmp:
            index = Path(tmp) / "index"
            self._git("read-tree", parent, index=index)
            for path in paths:
                if (path not in tracked or not _path_allowed(self.root,path,lease.allowed_paths)
                        or any(x in {".git",".agent"} for x in path.split("/"))):
                    raise CommitError("PATH_OUTSIDE_TRACKED_SCOPE")
                mode, kind, _ = tracked[path]
                if kind != "blob" or mode not in {"100644","100755"}:
                    raise CommitError("UNSUPPORTED_COMMIT_OBJECT")
                data = self._read(path)
                if self.accepted_edit is not None and (
                        paths!=(self.accepted_edit[0],)
                        or sha256(data).hexdigest()!=self.accepted_edit[1]):
                    raise CommitError("BROKER_ACCEPTED_EDIT_MISMATCH")
                oid = self._sha("hash-object","-w","--no-filters","--stdin",data=data)
                self._git("update-index","--cacheinfo",mode,oid,path,index=index)
            tree = self._sha("write-tree",index=index)
        if self.accepted_edit is not None:
            path,expected=self.accepted_edit
            if paths!=(path,) or sha256(self._read(path)).hexdigest()!=expected:
                raise CommitError("BROKER_ACCEPTED_EDIT_MISMATCH")
        if tree == self._sha("rev-parse",parent+"^{tree}"):
            raise CommitError("NO_COMMIT_CHANGE")
        return CandidateTree(parent, branch, tree, tuple(sorted(paths)),
                             self.authority.scope.task.session_id,
                             digest_json([list(c) for c in commands]))

    def commit(self, paths: tuple[str,...]):
        """Local ref CAS only, after verification of the exact candidate tree."""
        with self.authority._lock, self._lock:
            self.authority._require_started()
            self.authority._check("commit", paths)
            self.authority._check("test")
            commands = self._commands()
            candidate = self._prepare(paths,commands)
            result = self.verifier.verify(candidate, commands)
            if (not isinstance(result,VerificationResult)
                    or any(type(code) is not int for code in result.exit_codes)
                    or (result.tree,result.session,result.commands_digest) !=
                       (candidate.tree,candidate.session,candidate.commands_digest)
                    or result.exit_codes != (0,)*len(commands)
                    or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}",result.evidence_digest)):
                raise CommitError("VERIFICATION_NOT_BOUND_OR_FAILED")
            self.authority._check("commit",paths)
            self.authority._check("test")
            if self._prepare(paths, self._commands()) != candidate:
                raise CommitError("CANDIDATE_CHANGED_DURING_VERIFICATION")
            commit = self._sha("commit-tree",candidate.tree,"-p",candidate.parent,
                               "-m","HAA bounded task change [skip ci]")
            # Ref CAS then index-only reconciliation. No worktree reset or
            # unrelated staging changes. A failure between them leaves the
            # durable task intent unresolved; never auto-reset/retry.
            self.authority._check("commit",paths)
            if self._sha("write-tree") != self._sha("rev-parse",candidate.parent+"^{tree}"):
                raise CommitError("PREEXISTING_STAGED_CHANGES")
            self._git("update-ref",candidate.branch,commit,candidate.parent)
            self._git("read-tree",commit)
            if self._sha("write-tree") != candidate.tree:
                raise CommitError("CHECKOUT_RECONCILIATION_FAILED")
            return {"status":"COMMITTED_LOCAL","commit":commit,
                    "tree":candidate.tree,"evidenceDigest":result.evidence_digest,
                    "checkoutReconciliationRequired":False}
