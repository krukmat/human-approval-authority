"""Synthetic deterministic runner probe, never an authority source.

Execute only under dedicated worker UID 472, with a scratch fixture
named haa-delta-fixture. Uses the same worker proposal path and actual
runner main, real file tools, Git scope check and pinned command runner.
Only the model response and audit destination are test fixtures.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from scripts.haa.worker_runner import main as worker_main
from scripts.haa.runner_fixture_contract import BASE,NAME,CONTENT,card_bytes,initialize_repo

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=BASE/"scratch"/NAME


def fixture_runner(argv):
    sys.path.insert(0,str(ROOT/"scripts/local-agent"))
    import run_local_task as runner
    def tool(name,args):
        return {"tool_calls":[{"function":{"name":name,"arguments":json.dumps(args)}}]}
    responses=iter([tool("write_file",{"path":"README.md","content":CONTENT}),
                    tool("finish",{})])
    with patch.object(runner.gemma_local,"append_audit_log",return_value=None):
        return runner.main([*argv,"--context-provider","legacy"],
                           chat_fn=lambda messages:next(responses))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--socket",type=Path)
    p.add_argument("--prepare",action="store_true")
    args=p.parse_args()
    if (os.getuid()!=472 or os.geteuid()!=472 or FIXTURE!=FIXTURE.resolve()
            or (FIXTURE/"repo").resolve()!=FIXTURE/"repo"):
        raise SystemExit("SYNTHETIC_WORKER_REQUIRED")
    card=FIXTURE/"card.json"
    if args.prepare:
        if args.socket is not None:
            raise SystemExit("PREPARE_HAS_NO_SOCKET")
        FIXTURE.mkdir(mode=0o700)
        initialize_repo(FIXTURE/"repo")
        card.write_bytes(card_bytes())
        print("SYNTHETIC_WORKER_READY")
        return 0
    if args.socket is None or args.socket!=BASE/"ipc-probe"/"runner.sock":
        raise SystemExit("SYNTHETIC_SOCKET_REQUIRED")
    if card.read_bytes()!=card_bytes() or (FIXTURE/"out.json").exists():
        raise SystemExit("FRESH_SYNTHETIC_CARD_REQUIRED")
    return worker_main(["--socket",str(args.socket),"--scratch",str(FIXTURE/"repo"),
        "--card",str(card),"--out",str(FIXTURE/"out.json"),"--path","README.md"],
        run_scratch=fixture_runner)


if __name__=="__main__":
    raise SystemExit(main())
