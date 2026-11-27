"""Read-only protected executor deployment preflight. Never provisions users."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


class HostBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostLayout:
    executor_uid: int
    worker_uid: int
    install: Path
    state: Path
    target: Path
    scratch: Path


def _check_chain(path: Path, owner: int, *, private: bool = False):
    if not path.is_absolute() or path != path.resolve():
        raise HostBoundaryError("PATH_NOT_CANONICAL")
    for parent in (path, *path.parents):
        st = parent.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid not in {0, owner}:
            raise HostBoundaryError("UNTRUSTED_DIRECTORY_OWNER")
        if st.st_mode & 0o022:
            raise HostBoundaryError("WRITABLE_DIRECTORY_CHAIN")
    st = path.stat()
    if st.st_uid != owner or (private and st.st_mode & 0o077):
        raise HostBoundaryError("INVALID_DIRECTORY_PERMISSIONS")


def validate_layout(layout: HostLayout, *, effective_uid: int | None = None):
    """Necessary DAC conditions, not proof of ACL, sudo or keychain isolation."""
    uid = os.geteuid() if effective_uid is None else effective_uid
    if (type(layout.executor_uid) is not int or type(layout.worker_uid) is not int
            or min(layout.executor_uid, layout.worker_uid) <= 0
            or layout.executor_uid == layout.worker_uid
            or uid != layout.executor_uid):
        raise HostBoundaryError("EXECUTOR_IDENTITY_MISMATCH")
    _check_chain(layout.install, 0)
    _check_chain(layout.state, layout.executor_uid, private=True)
    _check_chain(layout.target, layout.executor_uid, private=True)
    _check_chain(layout.scratch, layout.worker_uid, private=True)
    roots = (layout.install, layout.state, layout.target, layout.scratch)
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
           for i, a in enumerate(roots) for b in roots[i+1:]):
        raise HostBoundaryError("OVERLAPPING_SECURITY_DOMAINS")
    return {"status": "DAC_PREFLIGHT_PASS", "isolation_certified": False}


def read_private_file(path: Path, *, owner_uid: int, max_bytes: int = 65536) -> bytes:
    """Read only a private, single-link regular file; parent must be protected."""
    _check_chain(path.parent, owner_uid, private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != owner_uid
                or st.st_mode & 0o077 or st.st_nlink != 1):
            raise HostBoundaryError("UNSAFE_PRIVATE_FILE")
        data = stream.read(max_bytes + 1)
    if not data or len(data) > max_bytes:
        raise HostBoundaryError("INVALID_PRIVATE_FILE_SIZE")
    return data
