from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock,patch
import subprocess
import unittest

from scripts.haa.contracts import digest_json
from scripts.haa.plan_closure import ClosureError
from scripts.haa.protected_plan_entry import ApprovedPlan,initialize_plan,PlanCloseController


class PlanEntryTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name).resolve()
        root=base/"repo";root.mkdir()
        self.state=base/"state";self.state.mkdir(mode=0o700)
        self.layout=SimpleNamespace(target=root,state=self.state)
        self.git("init","-b","candidate")
        self.git("config","user.name","test")
        self.git("config","user.email","test@example.invalid")
        self.git("remote","add","origin","https://github.com/example/workflow-fixture.git")
        (root/"docs").mkdir()
        (root/"docs/p.md").write_text("# p")
        (root/"docs/tasks.md").write_text("- [x] t")
        self.git("add","docs")
        self.git("commit","-m","approved")
        self.approved=ApprovedPlan("example/workflow-fixture","p","candidate",
            self.git("rev-parse","HEAD"),"docs/p.md",sha256(b"# p").hexdigest(),
            "docs/tasks.md",sha256(b"- [x] t").hexdigest(),("t",))
        m=patch("scripts.haa.protected_plan_entry.validate_layout");m.start();self.addCleanup(m.stop)

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.layout.target),*args],
            stderr=subprocess.DEVNULL,text=True).strip()

    def init(self,approved=None):
        return initialize_plan(layout=self.layout,approved=approved or self.approved,
                               directory=self.state,signing_key=b"K"*32)

    def test_no_import_of_markdown_completion(self):
        plan=self.init()
        self.assertEqual(plan.read_snapshot().workflow_state,"ACTIVE")
        self.assertEqual(plan.read_snapshot().completed_tasks,())

    def test_wrong_document_digest_denies_initialization(self):
        with self.assertRaisesRegex(ClosureError,"PLAN_DOCUMENT_DIGEST_MISMATCH"):
            self.init(replace(self.approved,plan_sha256="a"*64))

    def test_independent_closure_requires_completed_tasks_and_idle(self):
        plan=self.init()
        idle=Mock();verify=Mock()
        c=PlanCloseController(layout=self.layout,approved=self.approved,journal=plan,
            supervisor_lock=RLock(),assert_no_active_tasks=idle,verify_plan=verify)
        with self.assertRaisesRegex(ClosureError,"PLAN_TASKS_INCOMPLETE"):
            c.mark_ready()
        idle.assert_called_once()
        verify.assert_not_called()
        self.assertEqual(c.projection()["state"],"ACTIVE")
        plan.begin_task_completion(task_id="t",session_id="s")
        plan.record_verified_task(task_id="t",session_id="s",
            completion={"commit":self.approved.base_commit,"tree":"b"*40,
                        "evidenceDigest":digest_json({"fixture":"verified"})})
        verify.return_value={"status":"PASS","head":self.approved.base_commit,
                             "evidenceDigest":digest_json({"fixture":"plan-pass"})}
        self.assertEqual(c.mark_ready().workflow_state,"PLAN_READY_FOR_APPROVAL")
        requester=Mock()
        (self.layout.target/"docs/p.md").write_text("changed")
        with self.assertRaisesRegex(ClosureError,"CLOSURE_WORKTREE_NOT_CLEAN"):
            c.request_close(requester)
        requester.request_approval.assert_not_called()
