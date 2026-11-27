#!/usr/bin/env python3
"""Read-only known-path inventory, not an isolation or deployment certificate."""
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys


def metadata(path):
    try:
        s=path.lstat()
        return {"status":"PRESENT","uid":s.st_uid,"gid":s.st_gid,
                "mode":oct(stat.S_IMODE(s.st_mode)),
                "kind":"symlink" if stat.S_ISLNK(s.st_mode) else
                       "directory" if stat.S_ISDIR(s.st_mode) else
                       "file" if stat.S_ISREG(s.st_mode) else "other"}
    except FileNotFoundError:
        return {"status":"NOT_FOUND"}
    except PermissionError:
        return {"status":"NOT_ACCESSIBLE"}
    except OSError:
        return {"status":"UNKNOWN"}


def identity(uid):
    try:
        result=subprocess.run(["/usr/bin/id","-G",str(uid)],capture_output=True,
                              text=True,timeout=10,check=False)
        if result.returncode:
            return {"status":"UNRESOLVED"}
        return {"status":"RESOLVED","groups":[int(v) for v in result.stdout.split()]}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {"status":"UNKNOWN"}


def main():
    if platform.system()!="Darwin" or os.geteuid()==0:
        print(json.dumps({"status":"BLOCKED","reason":"MACOS_OWNER_NONROOT_REQUIRED"}))
        return 1
    paths=[]
    for base in (Path("/Library/DubBridgeHAA"),Path("/Library/WorkflowHAA")):
        paths.extend([base,*[base/n for n in ("code","state","target","scratch","exports",
                                              "verifier-work","ipc-probe")]])
    framework=Path("/Library/Frameworks/Python.framework/Versions/3.14")
    paths.extend([framework.parent,framework,framework/"bin",
                  framework/"bin/python3.14",framework/"lib/python3.14/site-packages"])
    result={"schema":"workflow.shared-host-inventory.v1",
            "status":"INVENTORY_ONLY","platform":platform.machine(),
            "candidate_identities":{str(uid):identity(uid) for uid in (471,472,473)},
            "paths":{str(p):metadata(p) for p in paths},
            "limitations":["No private content, ACL, sudo-policy or runtime dependency validation.",
                           "Inaccessible entries and unresolved identities must be reconciled.",
                           "No host isolation or physical authority certification."],
            "privileged_changes":False,"activation":"NO_GO"}
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
