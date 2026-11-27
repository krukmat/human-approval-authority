"""Submit a single existing-file edit from scratch, without model or HAA credentials.

Run as the separately provisioned worker UID. The protected broker still
checks kernel peer identity, live lease, preimage and actual target scope.
This is not a general shell executor and it cannot create or delete files.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from scripts.haa.worker_runner import _file
from scripts.haa.protected_broker import send_proposal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket",type=Path,required=True)
    parser.add_argument("--scratch",type=Path,required=True)
    parser.add_argument("--path",required=True)
    parser.add_argument("--before-sha256",required=True)
    args=parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{64}",args.before_sha256):
            raise ValueError("INVALID_PREIMAGE")
        target=_file(args.scratch.resolve(),args.path)
        content=target.read_bytes().decode("utf-8")
        expected=sha256(content.encode("utf-8")).hexdigest()
        status=send_proposal(args.socket,{"op":"status"})
        if status.get("status")!="BROKER_REACHABLE" or not isinstance(status.get("window"),str):
            raise RuntimeError("BROKER_UNAVAILABLE")
        response=send_proposal(args.socket,{"op":"replace","window":status["window"],
            "path":args.path,"before_sha256":args.before_sha256,"content":content})
        print(json.dumps(response))
        return 0 if response.get("status")=="REPLACED" and response.get("sha256")==expected else 1
    except Exception:
        print(json.dumps({"status":"BLOCKED"}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
