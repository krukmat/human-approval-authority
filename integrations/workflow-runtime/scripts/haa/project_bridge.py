"""Project-specific invocation adapters; no policy calculation or model call.

The existing project controller resolves the route, reviews, QA, fallback and
HITL gates. These functions only translate a selected route into argv for
an UNPRIVILEGED scratch runner. The executor must never execute this argv.
Cloud implementations submit the same typed batch from scratch.
"""
from dataclasses import dataclass
from pathlib import Path
import re


class BridgeError(ValueError):
    pass


@dataclass(frozen=True)
class Invocation:
    argv: tuple[str, ...]
    cwd: Path


def _absolute(path):
    if not isinstance(path, Path) or not path.is_absolute() or path.resolve()!=path:
        raise BridgeError("CANONICAL_ABSOLUTE_PATH_REQUIRED")
    return path


def local_invocation(*, repository, rri, task_id, paths, python, scratch,
                     runner, input_file, output_file, dry_run=False):
    """Build existing CLI only; never infer that local delegation is eligible."""
    for p in (python,scratch,runner,input_file,output_file):
        _absolute(p)
    if not scratch.is_dir() or not runner.is_file() or not input_file.is_file():
        raise BridgeError("RUNNER_INPUT_MISSING")
    if (input_file.is_relative_to(scratch) or output_file.is_relative_to(scratch)
            or input_file==output_file):
        raise BridgeError("WORKER_METADATA_MUST_BE_OUTSIDE_SCRATCH")
    if type(rri) is not int or rri<0 or type(dry_run) is not bool:
        raise BridgeError("INVALID_ROUTE_CONTEXT")
    if not isinstance(task_id,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}",task_id):
        raise BridgeError("INVALID_TASK_ID")
    if not isinstance(paths,tuple) or not paths or len(set(paths))!=len(paths):
        raise BridgeError("INVALID_SCOPE")
    for p in paths:
        if (not isinstance(p,str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,512}",p)
                or any(c.lower() in {"",".","..",".git",".agent"} for c in p.split("/"))):
            raise BridgeError("INVALID_SCOPE")
    if repository=="krukmat/fenix":
        if rri>25:
            raise BridgeError("FENIX_HIGH_BAND_LOCAL_NOT_ALLOWED")
        if runner.name!="delegate-low-rri.py":
            raise BridgeError("INVALID_FENIX_ENTRYPOINT")
        scope=tuple(x for p in paths for x in ("--allow-path",p))
        argv=(str(python),"-B",str(runner),str(input_file),
              "--repo-root",str(scratch),"--task-id",task_id,*scope,
              "--out",str(output_file),"--apply")
        if dry_run:
            argv=(*argv,"--dry-run")
    elif repository=="krukmat/dubbridge":
        if runner.name!="run_local_task.py" or dry_run:
            raise BridgeError("INVALID_DUBBRIDGE_ENTRYPOINT_OR_DRY_RUN")
        argv=(str(python),"-B",str(runner),"--card",str(input_file),
              "--worktree",str(scratch),"--out",str(output_file))
    else:
        raise BridgeError("UNSUPPORTED_PROJECT")
    return Invocation(argv,scratch)
