"""Cooperative HITL gate: no protected runtime, no real models or network."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import subprocess
import unittest

from scripts.haa.adapter import CheckpointBlocked, task_checkpoint
from scripts.haa.contracts import digest_json
from scripts.haa.protected_integration_test import FakeHaa


class TaskCheckpointTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.git("init","-b","main")
        self.git("config","user.name","fixture")
        self.git("config","user.email","fixture@example.invalid")
        self.git("remote","add","origin","https://github.com/fixture/workflow.git")
        for path,content in (("card.md","Existing task card"),("prompt.txt","Existing prompt"),
                             ("policy.md","Existing HITL policy"),("README.md","Before")):
            (self.root/path).write_text(content)
        self.git("add",".");self.git("commit","-m","fixture")
        self.haa=FakeHaa()
        self.config=dict(repository="fixture/workflow",repo_root=self.root,plan_id="p",task_id="t",
                         rri=42,task_card=self.root/"card.md",prompt_file=self.root/"prompt.txt",
                         allowed_paths=("README.md",),capabilities=("edit","test"),
                         policy_files=("policy.md",),wait_seconds=60,
                         requester=self.haa,executor=self.haa)

    def git(self,*args):
        return subprocess.check_output(["git","-C",str(self.root),*args],
                        stderr=subprocess.DEVNULL,text=True).strip()

    def approve(self,request_id):
        self.haa.approve_fixture(request_id)

    def test_exact_signed_checkpoint_pass_does_not_execute_or_mutate(self):
        before=self.git("rev-parse","HEAD")
        result=task_checkpoint(**self.config,on_pending=self.approve)
        self.assertEqual(result["status"],"CHECKPOINT_PASS")
        self.assertEqual(result["enforcement"],"COOPERATIVE_ONLY")
        self.assertEqual(self.haa.consumed,[result["requestId"]])
        self.assertEqual(self.git("rev-parse","HEAD"),before)
        self.assertEqual(self.git("status","--porcelain"),"")
        self.assertNotIn("signature",result)
        self.assertNotIn("grant",result)

    def test_pending_never_consumes_and_local_timeout_blocks(self):
        with self.assertRaisesRegex(CheckpointBlocked,"WAIT_TIMED_OUT"):
            task_checkpoint(**self.config,clock=Mock(side_effect=[0,0,1,61]),pause=lambda _:None)
        self.assertFalse(self.haa.consumed)
        self.assertEqual(len(self.haa.requests),1)

    def test_terminal_remote_states_block(self):
        for state in ("REJECTED","REVOKED","EXPIRED","CONSUMED","UNKNOWN"):
            with self.subTest(state=state),self.assertRaises(CheckpointBlocked):
                task_checkpoint(**self.config,
                    on_pending=lambda rid:self.haa.requests[rid].update(state=state))
        self.assertFalse(self.haa.consumed)

    def test_prompt_card_and_policy_drift_blocks_before_consumption(self):
        for name in ("prompt.txt","card.md","policy.md"):
            path=self.root/name
            original=path.read_bytes()
            def mutate(rid):
                self.approve(rid)
                path.write_bytes(original+b"changed")
            try:
                with self.subTest(path=name),self.assertRaisesRegex(CheckpointBlocked,"TASK_CHANGED"):
                    task_checkpoint(**self.config,on_pending=mutate)
                self.assertFalse(self.haa.consumed)
            finally:
                path.write_bytes(original)

    def test_git_head_and_branch_drift_blocks_before_consumption(self):
        def mutate(rid):
            self.approve(rid)
            self.git("switch","-c","different")
        with self.assertRaisesRegex(CheckpointBlocked,"TASK_CHANGED"):
            task_checkpoint(**self.config,on_pending=mutate)
        self.assertFalse(self.haa.consumed)

    def test_request_binding_mismatch_blocks(self):
        def tamper(rid):
            self.approve(rid)
            self.haa.requests[rid]["actionDigest"]="wrong"
        with self.assertRaisesRegex(CheckpointBlocked,"REQUEST_BINDING_CHANGED"):
            task_checkpoint(**self.config,on_pending=tamper)
        self.assertFalse(self.haa.consumed)

    def test_invalid_signature_never_passes(self):
        actual=self.haa.authorize
        def tamper(**kwargs):
            grant=actual(**kwargs)
            return {**grant,"signature":"AAAA"}
        with patch.object(self.haa,"authorize",side_effect=tamper):
            with self.assertRaisesRegex(CheckpointBlocked,"AUTHORIZATION_UNCERTAIN"):
                task_checkpoint(**self.config,on_pending=self.approve)
        self.assertEqual(len(self.haa.consumed),1)
        self.assertEqual(len(self.haa.requests),1)

    def test_network_failure_does_not_retry(self):
        with patch.object(self.haa,"request_approval",side_effect=OSError("network")) as call:
            with self.assertRaisesRegex(CheckpointBlocked,"HAA_UNAVAILABLE"):
                task_checkpoint(**self.config)
            call.assert_called_once()
        with patch.object(self.haa,"authorize",side_effect=OSError("network")) as call:
            with self.assertRaisesRegex(CheckpointBlocked,"AUTHORIZATION_UNCERTAIN"):
                task_checkpoint(**self.config,on_pending=self.approve)
            call.assert_called_once()

    def test_scope_and_commit_denied_before_request(self):
        for update in ({"capabilities":("commit",)},{"allowed_paths":("../escape",)},
                       {"repository":"wrong/project"},{"policy_files":()}):
            with self.subTest(update=update),self.assertRaises(Exception):
                task_checkpoint(**{**self.config,**update})
        self.assertFalse(self.haa.requests)

    def test_change_during_consume_blocks_dispatch(self):
        actual=self.haa.authorize
        def mutate(**kwargs):
            grant=actual(**kwargs)
            (self.root/"prompt.txt").write_text("changed after consume")
            return grant
        with patch.object(self.haa,"authorize",side_effect=mutate):
            with self.assertRaisesRegex(CheckpointBlocked,"TASK_CHANGED_AFTER_CONSUMPTION"):
                task_checkpoint(**self.config,on_pending=self.approve)
        self.assertEqual(len(self.haa.consumed),1)

    def test_distinct_prompt_and_card_are_bound_without_uploading_text(self):
        with self.assertRaisesRegex(CheckpointBlocked,"HAA_REJECTED"):
            def reject(rid):
                self.haa.requests[rid]["state"]="REJECTED"
            task_checkpoint(**self.config,on_pending=reject)
        first=next(iter(self.haa.requests.values()))["actionDigest"]
        (self.root/"prompt.txt").write_text("Different prompt")
        task_checkpoint(**self.config,on_pending=self.approve)
        self.assertNotEqual(first,self.haa.requests["request-2"]["actionDigest"])


if __name__=="__main__":
    unittest.main()
