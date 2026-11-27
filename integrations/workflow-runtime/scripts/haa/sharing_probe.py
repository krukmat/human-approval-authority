"""Bounded synthetic sharing-access probe. Never scans user directories."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat

BASE=Path("/Library/WorkflowHAA/sharing-probes")
NAMES=("private-canary","shared-canary","writable-canary")


def probe(root:Path):
    if (root!=root.resolve() or root.parent!=BASE or
            not root.name.startswith("fixture-") or os.geteuid() not in (471,472,473)):
        raise ValueError("SYNTHETIC_FIXTURE_REQUIRED")
    result={}
    for name in NAMES:
        target=root/name
        outcome={}
        for access,flag in (("read",os.O_RDONLY),("write_open",os.O_WRONLY)):
            try:
                fd=os.open(target,flag|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(fd,"rb" if access=="read" else "wb") as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                        raise ValueError("INVALID_SYNTHETIC_CANARY")
                    # Do not read content or change bytes. Opening a descriptor
                    # without O_TRUNC is sufficient to observe access.
                    outcome[access]="ALLOWED"
            except PermissionError:
                outcome[access]="DENIED"
            except OSError:
                outcome[access]="BLOCKED"
        result[name]=outcome
    return {"schema":"workflow.sharing-probe.v1","uid":os.geteuid(),
        "groups":sorted(os.getgroups()),"observations":result,
        "certified":False,"activation":"NO_GO"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("fixture",type=Path)
    args=p.parse_args()
    print(json.dumps(probe(args.fixture),indent=2,sort_keys=True))


if __name__=="__main__":
    main()
