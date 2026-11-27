"""D3 host probe; synthetic HAA signatures, actual distinct worker/verifier.

Never run as root or against any existing plan. No actual HAA endpoint,
secrets, biometrics, push or merge. Requires a separately provisioned
narrow IPC group and an already reconciled global verifier quarantine.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import stat
import sys

from scripts.haa.runner_fixture_contract import (
    BASE,NAME,CONTENT,REPOSITORY,COMMAND,CARD,initialize_repo,git,
)
from scripts.haa.protected_host import HostLayout,validate_layout
from scripts.haa.protected_plan_entry import ApprovedPlan,initialize_plan
from scripts.haa.protected_plan_validation import PlanValidation
from scripts.haa.protected_session import ProtectedSession
from scripts.haa.protected_supervisor import ProtectedSupervisor
from scripts.haa.live_verify import TrustedTask
from scripts.haa.policy import pin_policy
from scripts.haa.request_checkpoint import CheckpointStore
from scripts.haa.volatile_authority import AdmissionJournal,VolatileLeaseStore
from scripts.haa.protected_integration_test import FakeHaa
from scripts.haa.verification_backend import ExactTreeVerifier,VerificationIdentity
from scripts.haa.macos_verifier_launcher import MacOSVerifierLauncher

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipc-gid",type=int,required=True)
    args=parser.parse_args()
    if (os.getuid()!=471 or os.geteuid()!=471 or ROOT!=BASE/"code"
            or args.ipc_gid in (0,471,472,473)
            or args.ipc_gid not in {*os.getgroups(),os.getgid()}):
        raise SystemExit("SYNTHETIC_EXECUTOR_AND_IPC_GROUP_REQUIRED")
    if (BASE/"state"/"verifier-in-flight").exists():
        raise SystemExit("GLOBAL_VERIFIER_QUARANTINE")
    ipc=BASE/"ipc-probe"
    st=ipc.lstat()
    if (ipc!=ipc.resolve() or not stat.S_ISDIR(st.st_mode)
            or st.st_uid!=471 or st.st_gid!=args.ipc_gid
            or stat.S_IMODE(st.st_mode)!=0o750):
        raise SystemExit("INVALID_SYNTHETIC_IPC_DIRECTORY")
    socket_path=ipc/"runner.sock"
    state=BASE/"state"/NAME
    target=BASE/"target"/NAME
    if any(p.exists() or p.is_symlink() for p in (state,target,socket_path)):
        raise SystemExit("SYNTHETIC_RESOURCES_ALREADY_EXIST")
    os.umask(0o077)
    state.mkdir(mode=0o700)
    head=initialize_repo(target)
    layout=HostLayout(471,472,ROOT,state,target,BASE/"scratch")
    validate_layout(layout)
    plan_dir=state/"plan";plan_dir.mkdir(mode=0o700)
    journal_dir=state/"admission";journal_dir.mkdir(mode=0o700)
    approved=ApprovedPlan(REPOSITORY,"p","candidate",head,
        "docs/p.md",sha256((target/"docs/p.md").read_bytes()).hexdigest(),
        "docs/tasks.md",sha256((target/"docs/tasks.md").read_bytes()).hexdigest(),(NAME,))
    plan=initialize_plan(layout=layout,approved=approved,directory=plan_dir,
                         signing_key=os.urandom(32))
    AdmissionJournal.initialize(journal_dir)
    leases=VolatileLeaseStore(AdmissionJournal(journal_dir))
    checkpoints=CheckpointStore(state/"checkpoints",signing_key=os.urandom(32))
    sys.path.insert(0,str(ROOT/"scripts/local-agent"))
    from boundary import LocalAgentBoundary
    boundary=LocalAgentBoundary(str(target),["README.md"],[COMMAND])
    fixture=FakeHaa()
    identity=VerificationIdentity(471,472,473,473)
    launcher=MacOSVerifierLauncher(state=BASE/"state",identity=identity)
    verifier=ExactTreeVerifier(repo=target,exports=BASE/"exports",identity=identity,
                               launcher=launcher,timeout_seconds=15)
    task=TrustedTask(target,REPOSITORY,target/"card.json","fixture",
                     ("commit","edit","test"),300)
    policy_pin=pin_policy(root=target,repository=REPOSITORY,card_sha256=sha256((target/"card.json").read_bytes()).hexdigest(),
        rri=CARD["rri"],requires_haa=True,capabilities=task.capabilities,source_paths=("docs/p.md",),plan_close_requires_haa=True)
    session=ProtectedSession(layout=layout,task=task,policy_pin=policy_pin,
        card_sha256=sha256((target/"card.json").read_bytes()).hexdigest(),
        authoritative_rri=CARD["rri"],checkpoints=checkpoints,leases=leases,
        requester=fixture,executor=fixture,pin=fixture.pin,existing_boundary=boundary)
    supervisor=ProtectedSupervisor(layout=layout,approved=approved,plan=plan,
        verifier=verifier,plan_validation=PlanValidation(verifier=verifier,commands=(COMMAND,)))
    try:
        if supervisor.begin(session)!="WAITING_FOR_HUMAN":
            raise RuntimeError("SYNTHETIC_PENDING_REQUIRED")
        fixture.approve_fixture(next(iter(fixture.requests)))
        if supervisor.poll()!="APPROVED_NOT_CONSUMED":
            raise RuntimeError("SYNTHETIC_APPROVED_REQUIRED")
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            os.chown(socket_path,-1,args.ipc_gid)
            socket_path.chmod(0o660)
            listener.listen(4)
            print("SYNTHETIC_BROKER_READY",flush=True)
            result=supervisor.execute(listener,duration_seconds=90)
        if (result["status"]!="COMMITTED_LOCAL"
                or git(target,"rev-parse","HEAD")!=result["commit"]
                or (target/"README.md").read_text()!=CONTENT
                or plan.read_snapshot().completed_tasks!=(NAME,)
                or git(target,"status","--porcelain")):
            raise RuntimeError("SYNTHETIC_COMPLETION_MISMATCH")
        ready=supervisor.closure.mark_ready()
        if ready.workflow_state!="PLAN_READY_FOR_APPROVAL":
            raise RuntimeError("SYNTHETIC_CLOSURE_NOT_READY")
        # No plan-close grant or physical approval in D3. Final state must
        # remain ready, not done. Owner ceremony is a separate later gate.
        print(json.dumps({"status":"SYNTHETIC_D3_PASS",
            "executor_uid":os.geteuid(),"commit":result["commit"],
            "plan_state":ready.workflow_state,"completed_tasks":list(ready.completed_tasks),
            "fixture_authority":True,"physical_certification":False,
            "activation":"NO_GO"},sort_keys=True))
        return 0
    finally:
        leases.close()
        # Retain artifacts and socket path for explicit reconciliation.
        # No blanket cleanup or automatic retry.


if __name__=="__main__":
    raise SystemExit(main())
