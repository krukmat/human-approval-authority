#!/usr/bin/env python3
"""Read-only portable candidate gate. Does not install, activate, use secrets or Touch ID."""
from pathlib import Path
import json
import subprocess
import sys
import os
import shutil
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def step(label,argv,cwd,env,timeout=240):
    try:
        r=subprocess.run(argv,cwd=cwd,check=False,text=True,capture_output=True,timeout=timeout,env=env)
        return {"name":label,"status":"PASS" if r.returncode==0 else "FAIL",
                "exit_code":r.returncode,"output":r.stdout+r.stderr}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"name":label,"status":"BLOCKED","reason":type(e).__name__}


def main():
    if os.geteuid()==0:
        print(json.dumps({"status":"BLOCKED","reason":"NON_ROOT_REQUIRED","activation":"NO_GO"}))
        return 1
    node=shutil.which("node")
    if not node:
        print(json.dumps({"status":"BLOCKED","reason":"NODE_REQUIRED","activation":"NO_GO"}))
        return 1
    with TemporaryDirectory(prefix="workflow-portable-") as home:
        env={"PATH":os.pathsep.join([str(Path(sys.executable).parent),str(Path(node).resolve().parent),"/usr/bin","/bin"]),
             "HOME":home,"LANG":"C","PYTHONDONTWRITEBYTECODE":"1","GIT_CONFIG_NOSYSTEM":"1",
             "GIT_CONFIG_GLOBAL":"/dev/null","GIT_TERMINAL_PROMPT":"0"}
        before=step("clean-checkout",["/usr/bin/git","status","--porcelain"],REPO,env)
        if before["status"]!="PASS" or before["output"].strip():
            print(json.dumps({"status":"BLOCKED","reason":"CLEAN_CHECKOUT_REQUIRED","activation":"NO_GO"}))
            return 1
        head=step("head",["/usr/bin/git","rev-parse","HEAD"],REPO,env)
        if head["status"]!="PASS":
            print(json.dumps({"status":"BLOCKED","reason":"HEAD_UNAVAILABLE","activation":"NO_GO"}))
            return 1
        modules=[p.stem for p in (ROOT/"scripts/haa").glob("*_test.py")]
        steps=[step("profile-tests",[node,"--experimental-strip-types","--test",
                "tests/workflow-profiles.test.ts","tests/workflow-profile-parity.test.ts"],REPO,env),
            step("python-regression",[sys.executable,"-B","-m","unittest",*["scripts.haa."+m for m in sorted(modules)]],ROOT,env),
            step("task-card-parser",[sys.executable,"-B","-m","unittest","discover","-s","scripts/local-agent","-p","task_card_test.py"],ROOT,env),
            step("microbenchmark",[sys.executable,"-B","-m","scripts.haa.benchmark"],ROOT,env)]
        after=step("post-checkout",["/usr/bin/git","status","--porcelain"],REPO,env)
        if after["output"].strip(): after["status"]="FAIL"
        steps.append(after)
        end_head=step("head-after",["/usr/bin/git","rev-parse","HEAD"],REPO,env)
        if end_head["output"].strip()!=head["output"].strip(): end_head["status"]="FAIL"
        steps.append(end_head)
    result={"schema":"workflow.portable-gate.v1","steps":steps,
        "head":head["output"].strip(),"python":sys.version.split()[0],
        "runner_contract_integration":"NOT_RUN_EXTERNAL_RUNNER_REQUIRED",
        "status":"PASS_PORTABLE_ONLY" if all(x["status"]=="PASS" for x in steps) else "BLOCKED_OR_FAIL",
        "host_isolation":"NOT_TESTED","real_runner":"NOT_CERTIFIED","touch_id":"NOT_TESTED","activation":"NO_GO"}
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="PASS_PORTABLE_ONLY" else 1


if __name__=="__main__":
    raise SystemExit(main())
