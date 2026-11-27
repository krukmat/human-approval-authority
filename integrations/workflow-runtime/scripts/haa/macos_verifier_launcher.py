"""Candidate narrow sudo-to-verifier launcher; no installation or root execution.

Deployment must approve the exact root-owned helper and sudo rule. This
module never installs accounts, modifies sudoers or grants permissions.
Process-table observations are a necessary gate, not a sandbox certificate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import stat
import subprocess
from threading import RLock

from scripts.haa.verification_backend import VerificationError, VerificationIdentity

BASE = Path("/Library/WorkflowHAA")
HELPER = BASE / "bin/verify-launch"
EXPORTS = BASE / "exports"
WORK = BASE / "verifier-work"
PYTHON = Path("/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14")
ENV = {"PATH":"/usr/bin:/bin", "LANG":"C", "LC_ALL":"C", "HOME":"/var/empty"}


def _root_owned(path: Path):
    if path != path.resolve():
        raise VerificationError("LAUNCHER_PATH_NOT_CANONICAL")
    for item in (path, *path.parents):
        st=item.lstat()
        if (st.st_uid!=0 or st.st_mode & 0o022
                or (item==path and not stat.S_ISREG(st.st_mode))
                or (item!=path and not stat.S_ISDIR(st.st_mode))):
            raise VerificationError("UNTRUSTED_LAUNCHER_INSTALL")


def _idle(uid: int):
    result=subprocess.run(["/bin/ps","-ax","-o","uid=","-o","ruid=","-o","pid="],
        env=ENV,capture_output=True,text=True,timeout=10,check=False)
    if result.returncode or not result.stdout.strip():
        raise VerificationError("VERIFIER_PROCESS_TABLE_UNAVAILABLE")
    found=False
    for line in result.stdout.splitlines():
        parts=line.split()
        if len(parts)!=3 or not all(p.isdecimal() for p in parts):
            raise VerificationError("INVALID_VERIFIER_PROCESS_TABLE")
        if uid in (int(parts[0]),int(parts[1])):
            found=True
    if found:
        raise VerificationError("VERIFIER_PROCESS_RESIDUAL")


class MacOSVerifierLauncher:
    """Direct observed child exit, durable quarantine before each launch.

    The verifier UID is reserved for this service; no concurrent user,
    launchd job or agent may use it. A privileged administrator must
    establish that policy and prove cleanup, credentials and network
    isolation separately. Never clear the marker automatically on failure.
    """
    def __init__(self, *, state: Path, identity: VerificationIdentity):
        if platform.system()!="Darwin":
            raise VerificationError("MACOS_LAUNCHER_REQUIRED")
        identity.check()
        if state!=state.resolve():
            raise VerificationError("INVALID_LAUNCH_STATE")
        st=state.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=identity.executor_uid or st.st_mode & 0o077:
            raise VerificationError("INVALID_LAUNCH_STATE")
        self.state=state
        self.identity=identity
        self.marker=state/"verifier-in-flight"
        self._lock=RLock()

    def _sync(self):
        fd=os.open(self.state,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def run(self, argv: tuple[str,...], *, source: Path,
            identity: VerificationIdentity, timeout: int) -> int:
        with self._lock:
            if identity!=self.identity:
                raise VerificationError("LAUNCH_IDENTITY_CHANGED")
            identity.check()
            if (type(timeout) is not int or not 1<=timeout<=900
                    or not isinstance(argv,tuple) or not argv or len(argv)>128
                    or any(not isinstance(v,str) or not v or "\x00" in v for v in argv)):
                raise VerificationError("INVALID_LAUNCH_REQUEST")
            if (source!=source.resolve() or source.parent!=EXPORTS
                    or not source.name.startswith("verify-")):
                raise VerificationError("INVALID_LAUNCH_SOURCE")
            source_st=source.lstat()
            if (not stat.S_ISDIR(source_st.st_mode) or source_st.st_uid!=identity.executor_uid
                    or source_st.st_gid!=identity.verifier_gid
                    or stat.S_IMODE(source_st.st_mode)!=0o750):
                raise VerificationError("UNSAFE_LAUNCH_SOURCE")
            _root_owned(HELPER)
            _root_owned(PYTHON)
            payload=json.dumps({"schema":"workflow.verifier-launch.v2",
                "source":str(source),"argv":list(argv),
                "executor_uid":identity.executor_uid,
                "verifier_uid":identity.verifier_uid,"verifier_gid":identity.verifier_gid,
                "timeout_seconds":timeout},
                separators=(",",":")).encode()
            if len(payload)>65536:
                raise VerificationError("LAUNCH_REQUEST_TOO_LARGE")
            # O_EXCL is the cross-process admission lock and crash marker.
            # It persists through timeout, residual processes, or crash.
            try:
                fd=os.open(self.marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            except FileExistsError as exc:
                raise VerificationError("VERIFIER_QUARANTINED") from exc
            with os.fdopen(fd,"wb") as stream:
                stream.write(b"verification in flight\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._sync()
            _idle(identity.verifier_uid)
            result=subprocess.run(["/usr/bin/sudo","-n","-u",f"#{identity.verifier_uid}",
                "-g",f"#{identity.verifier_gid}","--",str(HELPER)],
                input=payload,env=ENV,cwd="/",stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=timeout+15,check=False,close_fds=True)
            _idle(identity.verifier_uid)
            # Timeout/monitor failure remain quarantined even if the process
            # table is empty. Never turn an ambiguous run into a clean retry.
            if result.returncode in (124,125) or result.returncode<0:
                raise VerificationError("VERIFIER_LAUNCH_AMBIGUOUS")
            # Other nonzero exits may be sudo denial or test failure.
            self.marker.unlink()
            self._sync()
            return result.returncode
