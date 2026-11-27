"""Unprivileged adapter for a policy-selected native runner and one batch.

The supervisor supplies the staged runner and worker identity. No credentials,
approval, privileged launch, model selection, retry or review is supplied
here. Existing policy gates must run before this worker is launched.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.haa.project_bridge import local_invocation
from scripts.haa.protected_broker import send_proposal
from scripts.haa.submit_batch import collect

ENV_KEYS=frozenset({"PATH","HOME","TMPDIR","TMP","TEMP","LANG","LC_ALL",
    "OLLAMA_HOST","FENIX_OLLAMA_HOST","FENIX_LOW_RRI_MODEL",
    "FENIX_LOW_RRI_NUM_CTX","FENIX_LOW_RRI_NUM_PREDICT","FENIX_LOW_RRI_TEMPERATURE",
    "FENIX_LOW_RRI_THINK","FENIX_LOW_RRI_IDLE_TIMEOUT_SECONDS",
    "FENIX_LOW_RRI_MAX_WALL_SECONDS"})


def run_native(*, worker_uid, repository, rri, task_id, paths, python, scratch,
               runner, input_file, output_file, socket_path):
    if type(worker_uid) is not int or worker_uid<=0 or worker_uid!=os.geteuid():
        raise RuntimeError("SEPARATE_WORKER_IDENTITY_REQUIRED")
    invocation=local_invocation(repository=repository,rri=rri,task_id=task_id,
        paths=paths,python=python,scratch=scratch,runner=runner,
        input_file=input_file,output_file=output_file)
    status=send_proposal(socket_path,{"op":"status"})
    if status.get("status")!="BROKER_REACHABLE" or not isinstance(status.get("window"),str):
        raise RuntimeError("BROKER_UNAVAILABLE")
    env={k:v for k,v in os.environ.items() if k in ENV_KEYS}
    env["PYTHONDONTWRITEBYTECODE"]="1"
    result=subprocess.run(invocation.argv,cwd=invocation.cwd,env=env,check=False)
    if result.returncode:
        raise RuntimeError("NATIVE_RUNNER_FAILED")
    changes=collect(scratch,paths)
    response=send_proposal(socket_path,{"op":"replace_batch","window":status["window"],
                                       "changes":changes})
    if response.get("status")!="BATCH_ACCEPTED" or response.get("paths")!=[c["path"] for c in changes]:
        raise RuntimeError("BATCH_NOT_ACCEPTED")
    return response


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-uid",type=int,required=True)
    parser.add_argument("--repository",required=True)
    parser.add_argument("--rri",type=int,required=True)
    parser.add_argument("--task-id",required=True)
    parser.add_argument("--path",action="append",required=True)
    for name in ("scratch","runner","input-file","output-file","socket"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        response=run_native(worker_uid=args.worker_uid,repository=args.repository,
            rri=args.rri,task_id=args.task_id,paths=tuple(args.path),
            python=Path(sys.executable).absolute(),scratch=args.scratch,runner=args.runner,
            input_file=args.input_file,output_file=args.output_file,socket_path=args.socket)
        print(json.dumps(response))
        return 0
    except Exception:
        print(json.dumps({"status":"BLOCKED"}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
