"""Synthetic incremental CPU/RSS and latency; no model, network or real HAA."""
import json
from pathlib import Path
import resource
import statistics
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from scripts.haa.contracts import build_task_start_action
from scripts.haa.policy import pin_policy


def measure(fn,n):
    samples=[]
    for _ in range(20): fn()
    cpu=process_time_ns()
    for _ in range(n):
        start=perf_counter_ns(); fn(); samples.append((perf_counter_ns()-start)/1000)
    cpu=(process_time_ns()-cpu)/1e6
    ordered=sorted(samples)
    return {"iterations":n,"p50_us":statistics.median(samples),
        "p95_us":ordered[min(n-1,(95*n+99)//100-1)],
        "p99_us":ordered[min(n-1,(99*n+99)//100-1)],"cpu_ms":cpu}


def main():
    with TemporaryDirectory() as d:
        root=Path(d); (root/"policy.md").write_text("synthetic-policy")
        p=pin_policy(root=root,repository="example/project",card_sha256="a"*64,rri=30,
            requires_haa=True,capabilities=("edit","test"),source_paths=("policy.md",),
            plan_close_requires_haa=False)
        def baseline():
            return {"repo":"example/project","task":"t","capabilities":("edit","test")}
        def with_authority():
            baseline()
            p.validate(root=root,repository="example/project",card_sha256="a"*64,rri=30,
                capabilities=("edit","test"))
            return build_task_start_action(repository="example/project",plan_id="p",task_id="t",
                session_id=p.digest(),branch="candidate",base_commit_sha="b"*40,
                allowed_paths=("README.md",),capabilities=("edit","test"),lease_ttl_seconds=300)
        n=1000
        base=measure(baseline,n); augmented=measure(with_authority,n)
        print(json.dumps({"schema":"workflow.synthetic-benchmark.v1","baseline":base,
            "with_policy_and_action":augmented,"p95_increment_us":augmented["p95_us"]-base["p95_us"],
            "peak_rss_native_units":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "model_calls":0,"tokens":0,"physical_ceremony":"NOT_TESTED",
            "scope":"microbenchmark only; not full workflow or remote HAA latency"},indent=2))


if __name__=="__main__":
    main()
