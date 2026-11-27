"""Bounded exact-tree verifier candidate; no provisioning or activation.

The protected executor exports immutable Git blobs. A deployment-approved
identity launcher MUST execute the pinned argv under a distinct, disposable
verification identity and return the actual child exit status. The model
worker is never that identity. No repository code runs as the executor.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import os
import posixpath
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unicodedata
from typing import Protocol

from scripts.haa.contracts import digest_json
from scripts.haa.protected_commit import CandidateTree, VerificationResult

_MAX_FILES = 8192
_MAX_BYTES = 128 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerificationIdentity:
    executor_uid: int
    agent_uid: int
    verifier_uid: int
    verifier_gid: int

    def check(self):
        uids=(self.executor_uid,self.agent_uid,self.verifier_uid)
        if (any(type(v) is not int or v <= 0 for v in (*uids,self.verifier_gid))
                or len(set(uids)) != 3 or os.geteuid()!=self.executor_uid):
            raise VerificationError("VERIFICATION_IDENTITY_NOT_SEPARATED")


class IdentityLauncher(Protocol):
    """Trusted host integration, NOT an agent or verifier-generated receipt.

    Implement only after actual UID/GID, process cleanup, read-only source,
    environment and non-elevation probes pass. Return the directly observed
    command exit status. Exceptions/timeout must block further runs until
    the host confirms all descendants are gone. No arbitrary root execution.
    """
    def run(self, argv: tuple[str,...], *, source: Path,
            identity: VerificationIdentity, timeout: int) -> int: ...


def _git(repo: Path, *args, data=None):
    result=subprocess.run(
        ["/usr/bin/git","-C",str(repo),"-c","core.hooksPath=/dev/null",
         "-c","core.fsmonitor=false",*args], input=data,capture_output=True,
        timeout=45,check=False,env={"PATH":"/usr/bin:/bin","HOME":"/var/empty",
          "LANG":"C","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
          "GIT_NO_REPLACE_OBJECTS":"1","GIT_TERMINAL_PROMPT":"0"})
    if result.returncode:
        raise VerificationError("EXACT_TREE_READ_FAILED")
    return result.stdout


def _entries(repo: Path, tree: str):
    if not isinstance(tree,str) or not _SHA.fullmatch(tree):
        raise VerificationError("INVALID_CANDIDATE_TREE")
    if _git(repo,"cat-file","-t",tree).strip()!=b"tree":
        raise VerificationError("NOT_A_TREE")
    entries=[]
    seen={}
    total=0
    for line in _git(repo,"ls-tree","-r","-l","-z",tree).split(b"\0"):
        if not line:
            continue
        meta,raw_path=line.split(b"\t",1)
        mode,kind,oid,size=meta.decode("ascii").split()
        path=raw_path.decode("utf-8")
        parts=path.split("/")
        if (mode not in {"100644","100755","120000"} or kind!="blob"
                or not _SHA.fullmatch(oid) or not size.isdecimal()
                or any(not p or p in {".",".."} or "\\" in p
                       or p.casefold()==".git" or any(ord(c)<32 for c in p) for p in parts)):
            raise VerificationError("UNSUPPORTED_TREE_ENTRY")
        # Reject case/normalization collisions, including directory prefixes.
        for i in range(1,len(parts)+1):
            prefix="/".join(parts[:i])
            key=unicodedata.normalize("NFD",prefix).casefold()
            if key in seen and seen[key]!=prefix:
                raise VerificationError("FILESYSTEM_NAME_COLLISION")
            seen[key]=prefix
        length=int(size)
        total+=length
        entries.append((path,mode,oid,length))
        if len(entries)>_MAX_FILES or total>_MAX_BYTES:
            raise VerificationError("TREE_EXPORT_LIMIT")
    if not entries:
        raise VerificationError("EMPTY_TREE")
    return entries


def _export(repo: Path, tree: str, destination: Path, gid: int):
    entries=_entries(repo,tree)
    raw=_git(repo,"cat-file","--batch",data="".join(
        oid+"\n" for _,_,oid,_ in entries).encode("ascii"))
    cursor=0
    links=[]
    for path,mode,oid,size in entries:
        end=raw.find(b"\n",cursor)
        if end<0 or raw[cursor:end]!=f"{oid} blob {size}".encode("ascii"):
            raise VerificationError("INVALID_BLOB_HEADER")
        start=end+1
        data=raw[start:start+size]
        cursor=start+size+1
        if (len(data)!=size or raw[cursor-1:cursor]!=b"\n"
                or sha1(f"blob {size}\0".encode()+data).hexdigest()!=oid):
            raise VerificationError("BLOB_INTEGRITY_FAILED")
        target=destination/path
        current=destination
        for component in target.relative_to(destination).parts[:-1]:
            current=current/component
            if not current.exists():
                current.mkdir(mode=0o750)
                os.chown(current,-1,gid)
                current.chmod(0o750)
        if mode=="120000":
            if not 0<len(data)<=4096:
                raise VerificationError("INVALID_SYMLINK_TARGET")
            link=data.decode("utf-8")
            normalized=posixpath.normpath(posixpath.join(posixpath.dirname(path),link))
            if (link.startswith("/") or "\x00" in link or "\\" in link
                    or normalized==".." or normalized.startswith("../")):
                raise VerificationError("SYMLINK_ESCAPES_TREE")
            links.append((target,link))
            continue
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchown(stream.fileno(),-1,gid)
            os.fchmod(stream.fileno(),0o550 if mode=="100755" else 0o440)
    if cursor!=len(raw):
        raise VerificationError("UNEXPECTED_BLOB_DATA")
    # Materialize links only AFTER all regular files. Never write through them.
    for target,link in links:
        target.symlink_to(link)
    for target,_ in links:
        try:
            resolved=target.resolve(strict=False)
        except (RuntimeError,OSError) as exc:
            raise VerificationError("SYMLINK_RESOLUTION_FAILED") from exc
        if not resolved.is_relative_to(destination):
            raise VerificationError("SYMLINK_ESCAPES_TREE")


class ExactTreeVerifier:
    """Concrete materialization and observed-exit adapter.

    The injected launcher is a trusted host dependency and has NO default.
    This class alone is not a verified OS sandbox or deployment certificate.
    The executor owns the export root, dedicated verifier group is read-only,
    and no other principal may be able to mutate the export tree.
    """
    def __init__(self, *, repo: Path, exports: Path, identity: VerificationIdentity,
                 launcher: IdentityLauncher, timeout_seconds: int=120):
        identity.check()
        if (launcher is None or type(timeout_seconds) is not int
                or not 1<=timeout_seconds<=900):
            raise VerificationError("INVALID_VERIFIER_CONFIGURATION")
        self.repo=repo.resolve()
        self.exports=exports.resolve()
        st=self.exports.lstat()
        if (exports!=self.exports or not stat.S_ISDIR(st.st_mode)
                or st.st_uid!=identity.executor_uid or st.st_gid!=identity.verifier_gid
                or stat.S_IMODE(st.st_mode)!=0o750
                or self.exports.is_relative_to(self.repo)
                or self.repo.is_relative_to(self.exports)):
            raise VerificationError("UNSAFE_VERIFICATION_EXPORT_ROOT")
        self.identity=identity
        self.launcher=launcher
        self.timeout=timeout_seconds
        self._blocked=False

    def verify(self,candidate: CandidateTree,commands: tuple[tuple[str,...],...]):
        if self._blocked:
            raise VerificationError("VERIFIER_REQUIRES_OPERATOR_RECONCILIATION")
        self.identity.check()
        if (not isinstance(commands,tuple) or not commands or len(commands)>32
                or any(not isinstance(c,tuple) or not c
                       or any(not isinstance(a,str) or not a or "\0" in a for a in c)
                       for c in commands)
                or digest_json([list(c) for c in commands])!=candidate.commands_digest):
            raise VerificationError("VERIFICATION_COMMAND_BINDING_MISMATCH")
        exits=[]
        # On an ambiguous launcher error, retain the export and latch the
        # instance closed. Durable task intent separately blocks workflow retry.
        source=Path(tempfile.mkdtemp(prefix="verify-",dir=self.exports))
        try:
            os.chown(source,-1,self.identity.verifier_gid)
            source.chmod(0o750)
            _export(self.repo,candidate.tree,source,self.identity.verifier_gid)
            for command in commands:
                code=self.launcher.run(command,source=source,identity=self.identity,
                                       timeout=self.timeout)
                if type(code) is not int:
                    raise VerificationError("INVALID_OBSERVED_EXIT_STATUS")
                exits.append(code)
                if code!=0:
                    break
        except BaseException:
            self._blocked=True
            raise
        else:
            import shutil
            try:
                shutil.rmtree(source)
            except OSError:
                self._blocked=True
                raise
        evidence=digest_json({"schema":"workflow.exact-tree-verification.v1",
            "tree":candidate.tree,"session":candidate.session,
            "commandsDigest":candidate.commands_digest,"exitCodes":exits})
        return VerificationResult(candidate.tree,candidate.session,candidate.commands_digest,
                                  tuple(exits),evidence)
