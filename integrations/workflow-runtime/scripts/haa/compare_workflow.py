"""Compare observed matched workflow replay pairs; never infer missing metrics."""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path


class EvidenceError(ValueError):
    pass


MATCH=("base_commit","task_digest","implementation_digest","checks_digest")
COUNTS=("model_calls","tokens","reviewer_calls","human_prompts","authorized_haa_prompts")
METRICS=("wall_ms","cpu_ms","peak_rss_bytes")


def percentile(values,p):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(p*len(ordered))-1)]


def compare(records):
    pairs=defaultdict(dict)
    for r in records:
        if not isinstance(r,dict) or r.get("schema")!="workflow.ab.observed.v1":
            raise EvidenceError("INVALID_SCHEMA")
        if (r.get("status")!="PASS" or r.get("variant") not in {"baseline","haa"}
                or not isinstance(r.get("pair_id"),str) or not r["pair_id"].strip()
                or r.get("provenance")!="OBSERVED_MATCHED_REPLAY"):
            raise EvidenceError("UNMATCHED_OR_UNVERIFIED_RUN")
        for key in MATCH:
            if not isinstance(r.get(key),str) or not r[key]:
                raise EvidenceError("MISSING_MATCH_BINDING:"+key)
        if not re.fullmatch(r"[0-9a-f]{40}",r["base_commit"]):
            raise EvidenceError("INVALID_BASE_COMMIT")
        for key in (*COUNTS,*METRICS):
            value=r.get(key)
            if type(value) not in {int,float} or not math.isfinite(value) or value<0:
                raise EvidenceError("MISSING_OR_INVALID_MEASUREMENT:"+key)
            if key in COUNTS and type(value) is not int:
                raise EvidenceError("INVALID_COUNT:"+key)
        if r["authorized_haa_prompts"]>r["human_prompts"]:
            raise EvidenceError("INVALID_PROMPT_ACCOUNTING")
        if r["variant"] in pairs[r["pair_id"]]:
            raise EvidenceError("DUPLICATE_VARIANT")
        pairs[r["pair_id"]][r["variant"]]=r
    if not pairs:
        raise EvidenceError("NO_MATCHED_PAIRS")
    deltas={key:[] for key in (*COUNTS,*METRICS)}
    violations=[]
    for identity, pair in sorted(pairs.items()):
        if set(pair)!={"baseline","haa"}:
            raise EvidenceError("INCOMPLETE_PAIR:"+identity)
        a,b=pair["baseline"],pair["haa"]
        if any(a[k]!=b[k] for k in MATCH):
            raise EvidenceError("CONTEXT_DRIFT:"+identity)
        if a["authorized_haa_prompts"]!=0:
            raise EvidenceError("BASELINE_HAS_HAA_PROMPTS")
        for key in deltas:
            deltas[key].append(b[key]-a[key])
        for key in ("model_calls","tokens","reviewer_calls"):
            if b[key]>a[key]:
                violations.append({"pair":identity,"reason":"ADDITIONAL_"+key.upper()})
        if b["human_prompts"]-a["human_prompts"]>b["authorized_haa_prompts"]:
            violations.append({"pair":identity,"reason":"UNAUTHORIZED_EXTRA_PROMPTS"})
    return {"schema":"workflow.ab.comparison.v1","matched_pairs":len(pairs),
            "status":"FAIL_GOVERNANCE_OVERHEAD" if violations else "MEASURED_NO_ADDITIONAL_MODEL_OVERHEAD",
            "deltas":{k:{"p50":percentile(v,.5),"p95":percentile(v,.95),"p99":percentile(v,.99),
                         "min":min(v),"max":max(v)} for k,v in deltas.items()},
            "violations":violations,"performance_threshold":"NOT_SET",
            "evidence_scope":"provided observed replay pairs; no host certification",
            "activation":"NO_GO"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence",type=Path)
    args=parser.parse_args()
    try:
        records=[json.loads(line) for line in args.evidence.read_text().splitlines() if line.strip()]
        report=compare(records)
    except (OSError,ValueError) as exc:
        report={"status":"BLOCKED","reason":str(exc),"activation":"NO_GO"}
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="MEASURED_NO_ADDITIONAL_MODEL_OVERHEAD" else 1


if __name__=="__main__":
    raise SystemExit(main())
