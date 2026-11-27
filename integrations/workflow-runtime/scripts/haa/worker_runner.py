"""Run the existing local runner in scratch; submit ONE bounded edit proposal.

No HAA credentials, authority activation, real plan completion or Git push.
A successful worker run is not trusted verification evidence. The protected
broker independently validates actual scope and live authority at application.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from scripts.haa.protected_broker import MAX_CONTENT, send_proposal

ROOT = Path(__file__).resolve().parents[2]


def _file(root: Path, relative: str):
    if (not relative or relative.startswith("/") or "\\" in relative
            or any(v in {"", ".", "..", ".git", ".agent"} for v in relative.split("/"))):
        raise ValueError("INVALID_WORKER_PATH")
    target = root / relative
    if target.resolve() != target or not target.is_file():
        raise ValueError("UNSAFE_WORKER_FILE")
    if target.stat().st_size > MAX_CONTENT:
        raise ValueError("WORKER_FILE_TOO_LARGE")
    return target


def main(argv=None, *, run_scratch=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket",type=Path,required=True)
    parser.add_argument("--scratch",type=Path,required=True)
    parser.add_argument("--card",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--path",required=True)
    parser.add_argument("--runner",type=Path)
    args=parser.parse_args(argv)
    root=args.scratch.resolve()
    try:
        target=_file(root,args.path)
        before=sha256(target.read_bytes()).hexdigest()
        status=send_proposal(args.socket,{"op":"status"})
        if status.get("status")!="BROKER_REACHABLE" or not isinstance(status.get("window"),str):
            raise RuntimeError("BROKER_UNAVAILABLE")
        # Actual historical common runner. No extra arbitrary CLI arguments.
        runner_args=["--card",str(args.card.resolve()),"--worktree",str(root),
                     "--out",str(args.out.resolve())]
        # Explicit Python-only test seam; no CLI fixture switch or trusted
        # authority is granted by this return code.
        if run_scratch is None:
            # The supervisor selects a repository-specific runner staged in
            # the protected installation. No fallback to target-repo code.
            runner=args.runner
            if (runner is None or not runner.is_absolute() or runner.resolve()!=runner
                    or not runner.is_relative_to(ROOT/"adapters")
                    or not runner.is_file()):
                raise RuntimeError("PINNED_RUNNER_REQUIRED")
            code=subprocess.run([sys.executable,str(runner),*runner_args],
                                cwd=root,check=False).returncode
        else:
            code=run_scratch(runner_args)
        if code:
            raise RuntimeError("SCRATCH_RUNNER_FAILED")
        target=_file(root,args.path)
        content=target.read_bytes().decode("utf-8")
        if sha256(content.encode()).hexdigest()==before:
            print(json.dumps({"status":"NO_CHANGE"}))
            return 0
        response=send_proposal(args.socket,{"op":"replace","window":status["window"],"path":args.path,
                                           "before_sha256":before,"content":content})
        print(json.dumps(response))
        return 0 if (response.get("status")=="REPLACED"
                     and response.get("sha256")==sha256(content.encode()).hexdigest()) else 1
    except Exception:
        print(json.dumps({"status":"BLOCKED"}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
