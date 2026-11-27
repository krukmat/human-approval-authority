#!/usr/bin/env python3
"""Read-only portable + native runner contract gate.

Uses real local project checkouts, their actual runner entrypoints, a
Fenix dry-run and mocked DubBridge runner contract tests. Never switches
branches, calls Ollama, provisions a host, requests Touch ID or activates HAA.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parent


def run(argv,cwd,env,timeout=300):
    return subprocess.run(argv,cwd=cwd,env=env,check=False,text=True,
                          capture_output=True,timeout=timeout)


def git(root,env,*argv):
    result=run(["/usr/bin/git","-C",str(root),*argv],root,env,30)
    if result.returncode:
        raise RuntimeError("GIT_INSPECTION_FAILED")
    return result.stdout.strip()


def snapshot(root,repository,env):
    if Path(git(root,env,"rev-parse","--show-toplevel")).resolve()!=root:
        raise RuntimeError("REPOSITORY_ROOT_MISMATCH")
    origin=git(root,env,"remote","get-url","origin")
    if origin not in {f"https://github.com/{repository}",f"https://github.com/{repository}.git",
                      f"git@github.com:{repository}.git",f"ssh://git@github.com/{repository}.git"}:
        raise RuntimeError("REPOSITORY_ORIGIN_MISMATCH")
    if git(root,env,"status","--porcelain","--untracked-files=normal"):
        raise RuntimeError("PROJECT_CHECKOUT_NOT_CLEAN")
    return git(root,env,"rev-parse","HEAD")


def check_project(repo,root,env,temp):
    record={"repository":repo,"status":"FAIL"}
    try:
        root=root.resolve()
        before=snapshot(root,repo,env)
        record["head"]=before
        if repo=="krukmat/fenix":
            scratch=temp/"scratch";scratch.mkdir()
            packet=temp/"fixture-packet.md";packet.write_text("Synthetic runner contract probe. No implementation.")
            out=temp/"fixture-result.json"
            sys.path.insert(0,str(ROOT))
            from scripts.haa.project_bridge import local_invocation
            runner=(root/"scripts/delegate-low-rri.py").resolve()
            call=local_invocation(repository=repo,rri=10,task_id="synthetic-probe",
                paths=("README.md",),python=Path(sys.executable).absolute(),scratch=scratch,
                runner=runner,input_file=packet,output_file=out,dry_run=True)
            result=run(call.argv,call.cwd,env,60)
            if result.returncode:
                raise RuntimeError("FENIX_DRY_RUN_FAILED:"+result.stderr[-4000:])
            payload=json.loads(result.stdout)
            if not isinstance(payload.get("messages"),list) or not payload["messages"] or out.exists():
                raise RuntimeError("FENIX_DRY_RUN_CONTRACT_FAILED")
            record["proof"]="NATIVE_DRY_RUN"
            record["payload_digest"]=hashlib.sha256(result.stdout.encode()).hexdigest()
        elif repo=="krukmat/dubbridge":
            runner=root/"scripts/local-agent/run_local_task.py"
            if not runner.is_file():
                raise RuntimeError("NATIVE_RUNNER_MISSING")
            native_env={**env,"PYTHONPATH":os.pathsep.join([str(runner.parent),str(root/"scripts")])}
            test=run([sys.executable,"-B","-m","unittest","discover","-s",
                      str(ROOT/"scripts/local-agent"),"-p","task_card_runner_integration_test.py"],
                     root,native_env,120)
            record["test_output"]=test.stdout+test.stderr
            if test.returncode:
                raise RuntimeError("DUBBRIDGE_RUNNER_CONTRACT_FAILED")
            record["proof"]="REAL_RUNNER_MOCKED_CONTRACT_TESTS"
        else:
            raise RuntimeError("UNSUPPORTED_PROJECT")
        if snapshot(root,repo,env)!=before:
            raise RuntimeError("PROJECT_HEAD_CHANGED")
        record["status"]="PASS"
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        record["reason"]=str(exc)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fenix",type=Path,required=True)
    parser.add_argument("--dubbridge",type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()==0:
        print(json.dumps({"status":"BLOCKED","reason":"NON_ROOT_REQUIRED","activation":"NO_GO"}))
        return 1
    node=shutil.which("node")
    if not node:
        print(json.dumps({"status":"BLOCKED","reason":"NODE_REQUIRED","activation":"NO_GO"}))
        return 1
    with TemporaryDirectory(prefix="haa-integration-") as directory:
        temp=Path(directory).resolve()
        home=temp/"home";home.mkdir()
        env={"PATH":os.pathsep.join([str(Path(sys.executable).parent),str(Path(node).resolve().parent),"/usr/bin","/bin"]),
             "HOME":str(home),"LANG":"C","PYTHONDONTWRITEBYTECODE":"1","GIT_CONFIG_NOSYSTEM":"1",
             "GIT_CONFIG_GLOBAL":"/dev/null","GIT_TERMINAL_PROMPT":"0"}
        try:
            portable=run([sys.executable,"-B",str(ROOT/"certify.py")],ROOT,env,600)
            portable_report=json.loads(portable.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            portable_report={"status":"BLOCKED","reason":str(exc)}
        records=[check_project("krukmat/fenix",args.fenix,env,temp),
                 check_project("krukmat/dubbridge",args.dubbridge,env,temp)]
    passed=(portable_report.get("status")=="PASS_PORTABLE_ONLY"
            and all(r["status"]=="PASS" for r in records))
    result={"schema":"workflow.integration-contract-gate.v1",
            "status":"PASS_RUNNER_CONTRACTS_ONLY" if passed else "BLOCKED_OR_FAIL",
            "portable":portable_report,"projects":records,
            "model_calls":0,"tokens":0,"actual_protected_runner":"NOT_CERTIFIED",
            "full_workflow_ab":"NOT_MEASURED","host_isolation":"NOT_TESTED",
            "touch_id":"NOT_TESTED","activation":"NO_GO"}
    print(json.dumps(result,indent=2))
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
