"""Trusted composition of a fixed native worker invocation.

Only constructs argv; never launches a process as executor. Deployment must
stage the pinned native runner and its dependencies in a protected install,
then launch this invocation as layout.worker_uid. Scratch metadata is
worker-private and is checked lexically, not read by the executor.
"""
from pathlib import Path
import re
from scripts.haa.protected_supervisor import WorkerInvocation, SupervisorError
from scripts.haa.live_verify import checked_bound_card
from scripts.haa.lease_guard import _path_allowed


def native_worker_invocation(*, layout, authority, python, socket_path, runner,
                             input_file, output_file, worktree, paths):
    with authority._lock:
        authority._require_started()
        authority._check("edit",paths)
        authority._check("commit",paths)
        authority._check("test")
        task=authority.scope.task
        card=checked_bound_card(task,task.repo_root.resolve(),required=True)
        if task.repo_root.resolve()!=layout.target:
            raise SupervisorError("PROTECTED_TARGET_REQUIRED")
        repository=task.repository
        expected={"krukmat/fenix":"delegate-low-rri.py",
                  "krukmat/dubbridge":"run_local_task.py"}.get(repository)
        if expected is None or runner.name!=expected:
            raise SupervisorError("INVALID_NATIVE_ENTRYPOINT")
        if repository=="krukmat/fenix" and card.rri>25:
            raise SupervisorError("FENIX_HIGH_BAND_LOCAL_NOT_ALLOWED")
        if (not python.is_absolute() or python.resolve()!=python
                or not runner.is_absolute() or runner.resolve()!=runner
                or not runner.is_relative_to(layout.install/"adapters")
                or not runner.is_file() or not socket_path.is_absolute()):
            raise SupervisorError("INVALID_STAGED_NATIVE_RUNNER")
        for value in (worktree,input_file,output_file):
            if (not value.is_absolute() or ".." in value.parts
                    or not value.is_relative_to(layout.scratch) or value==layout.scratch):
                raise SupervisorError("WORKER_PATH_OUTSIDE_SCRATCH")
        if (input_file.is_relative_to(worktree) or output_file.is_relative_to(worktree)
                or input_file==output_file):
            raise SupervisorError("WORKER_METADATA_IN_WORKTREE")
        lease=authority.leases.load(authority.scope.lease_id)
        if (not isinstance(paths,tuple) or not paths or len(set(paths))!=len(paths)
                or any(not isinstance(p,str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,512}",p)
                       or not _path_allowed(layout.target,p,lease.allowed_paths) for p in paths)):
            raise SupervisorError("NATIVE_WORKER_SCOPE_MISMATCH")
        for p in paths:
            authority.existing.check_write(p)
        bootstrap=("import sys; sys.path.insert(0,sys.argv.pop(1)); "
                   "from scripts.haa.native_batch_worker import main; raise SystemExit(main())")
        scope=tuple(x for p in paths for x in ("--path",p))
        argv=(str(python),"-I","-B","-c",bootstrap,str(layout.install),
              "--worker-uid",str(layout.worker_uid),"--repository",repository,
              "--task-id",card.task_id,"--rri",str(card.rri),
              "--scratch",str(worktree),"--runner",str(runner),
              "--input-file",str(input_file),"--output-file",str(output_file),
              "--socket",str(socket_path),*scope)
        return WorkerInvocation(argv,worktree)
