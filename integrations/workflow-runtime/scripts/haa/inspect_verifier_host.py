"""Read-only host prerequisites. No sudo, user creation, credential reads or HAA."""
from __future__ import annotations
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def run(argv):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=10,check=False)
        return p.returncode,p.stdout.strip()
    except (OSError,subprocess.TimeoutExpired):
        return None,""


def main():
    head_code,head=run(["git","-C",str(ROOT),"rev-parse","HEAD"])
    dirty_code,dirty=run(["git","-C",str(ROOT),"status","--porcelain"])
    info={"schema":"workflow.verifier-host-inventory.v1",
          "head":head if head_code==0 else None,
          "clean_checkout":dirty_code==0 and not dirty,
          "platform":platform.system(),"architecture":platform.machine(),
          "uid":os.geteuid(),"group_ids":sorted(set(os.getgroups())),
          "python":sys.version.split()[0],
          "privileged_changes":False,"isolation_certified":False,
          "activation":"NO_GO"}
    if platform.system()=="Darwin":
        code,raw=run(["/usr/bin/dscl",".","-list","/Users","UniqueID"])
        user_ids=[]
        if code==0:
            for line in raw.splitlines():
                fields=line.split()
                if len(fields)==2 and fields[1].isdigit():
                    uid=int(fields[1])
                    if uid>=500 and uid!=65534:
                        user_ids.append(uid)
        info["non_system_user_ids"]=sorted(set(user_ids)) if code==0 else None
        # Report actual group membership; no sudo-policy inference.
        import grp
        try:
            admin_gid=grp.getgrnam("admin").gr_gid
            info["current_user_in_admin_group"]=admin_gid in {*os.getgroups(),os.getegid()}
        except KeyError:
            info["current_user_in_admin_group"]=None
        tools={}
        for path in ("/usr/bin/sudo","/bin/launchctl","/usr/bin/git","/usr/bin/python3",
                     str(Path(sys.executable).resolve())):
            try:
                s=Path(path).stat()
                tools["current_python" if path==str(Path(sys.executable).resolve()) else path]={
                    "present":True,"owner_uid":s.st_uid,"mode":oct(stat.S_IMODE(s.st_mode))}
            except OSError:
                tools[path]={"present":False}
        info["tools"]=tools
    info["limitations"]=["No ACL, sudo policy, credential, or process isolation proof.",
                         "Inventory only; do not infer dedicated identities from UID counts."]
    print(json.dumps(info,indent=2,sort_keys=True))
    return 0 if head_code==0 and dirty_code==0 else 1


if __name__=="__main__":
    raise SystemExit(main())
