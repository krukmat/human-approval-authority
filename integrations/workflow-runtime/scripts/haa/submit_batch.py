"""Worker-only batch proposal from an existing scratch checkout.

No HAA credentials, privileged execution or automatic publication. Only
tracked text replacements are supported. The executor independently verifies
every preimage, scope, lease, candidate tree and exact test result.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from scripts.haa.batch_commit import parse_batch
from scripts.haa.protected_broker import send_proposal
from scripts.haa.worker_runner import _file


def git(root,*argv):
    return subprocess.check_output(["/usr/bin/git","-C",str(root),*argv],timeout=30)


def collect(root, paths):
    root=root.resolve()
    if Path(git(root,"rev-parse","--show-toplevel").decode().strip()).resolve()!=root:
        raise ValueError("SCRATCH_ROOT_MISMATCH")
    if len(set(paths))!=len(paths):
        raise ValueError("DUPLICATE_REQUESTED_PATH")
    # Require explicit complete set of modified tracked paths; reject staged,
    # created, deleted, renamed and untracked files. Ignored build output is
    # not a proposal and never copied to the protected executor.
    if git(root,"diff","--cached","--name-only","-z"):
        raise ValueError("SCRATCH_STAGED_CHANGES")
    if git(root,"ls-files","--others","--exclude-standard","-z"):
        raise ValueError("SCRATCH_UNTRACKED_CHANGES")
    actual=set(git(root,"diff","--name-only","-z","--no-renames","HEAD","--")
               .decode("utf-8").strip("\0").split("\0"))
    if actual!=set(paths):
        raise ValueError("SCRATCH_CHANGE_SET_MISMATCH")
    changes=[]
    for path in paths:
        target=_file(root,path)
        before=git(root,"show","HEAD:"+path)
        before.decode("utf-8")
        changes.append({"path":path,"before_sha256":sha256(before).hexdigest(),
                        "content":target.read_bytes().decode("utf-8")})
    proposal=parse_batch(changes)
    return [{"path":c.path,"before_sha256":c.before,"content":c.content}
            for c in proposal.changes]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket",type=Path,required=True)
    parser.add_argument("--scratch",type=Path,required=True)
    parser.add_argument("--path",action="append",required=True)
    args=parser.parse_args()
    try:
        changes=collect(args.scratch,args.path)
        status=send_proposal(args.socket,{"op":"status"})
        if status.get("status")!="BROKER_REACHABLE" or not isinstance(status.get("window"),str):
            raise RuntimeError("BROKER_UNAVAILABLE")
        response=send_proposal(args.socket,{"op":"replace_batch","window":status["window"],
                                          "changes":changes})
        print(json.dumps(response))
        return 0 if (response.get("status")=="BATCH_ACCEPTED" and
                     response.get("paths")==[c["path"] for c in changes]) else 1
    except Exception:
        print(json.dumps({"status":"BLOCKED"}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
