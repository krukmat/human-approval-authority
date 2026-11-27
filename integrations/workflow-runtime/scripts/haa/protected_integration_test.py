"""Synthetic end-to-end: real Git, SQLite, detached Ed25519 signatures.

Only the HAA transport, deployment proof and verification worker are
fixtures. No biometric, real HAA call, privileged installation or actual
plan closure. This is not a macOS isolation certificate.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from scripts.haa import grants
from scripts.haa.contracts import canonicalize,digest_json
from scripts.haa.live_verify import TrustedAuthorityPin,TrustedTask,bind_trusted_task
from scripts.haa.protected_broker import WorkerBroker
from scripts.haa.protected_commit import ProtectedCommit,VerificationResult
from scripts.haa.batch_commit import BatchCommit
from scripts.haa.protected_plan_entry import ApprovedPlan,initialize_plan,PlanCloseController
from scripts.haa.protected_workflow import ProtectedWorkflow
from scripts.haa.request_checkpoint import CheckpointStore,reconcile_status
from scripts.haa.runner_authority import (
    RunnerAuthority,RunnerScope,request_bound_task,activate_bound_task,
)
from scripts.haa.volatile_authority import AdmissionJournal,VolatileLeaseStore
from scripts.haa.authority_lease import LeaseError


class FakeHaa:
    """Transport fixture with a real ephemeral signing key and exact grants."""
    def __init__(self):
        self.private=grants.ed25519.Ed25519PrivateKey.generate()
        self.pem=self.private.public_key().public_bytes(
            grants.serialization.Encoding.PEM,
            grants.serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.pin=TrustedAuthorityPin("key",sha256(self.pem.encode()).hexdigest())
        self.config=SimpleNamespace(executor_audience="exec")
        self.requests={}
        self.consumed=[]

    def request_approval(self,action,*,ttl_ms):
        identity="request-"+str(len(self.requests)+1)
        item={"id":identity,"actionDigest":digest_json(action),
              "intent":{"executorAudience":"exec"},"state":"PENDING"}
        self.requests[identity]=item
        return dict(item)

    def get_request(self,request_id):
        return dict(self.requests[request_id])

    def authority_keys(self):
        return [{"keyId":"key","status":"ACTIVE","algorithm":"Ed25519","publicKeyPem":self.pem}]

    def approve_fixture(self,identity):
        self.requests[identity]["state"]="APPROVED"

    def authorize(self,*,request_id,execution_id,actual_action,actual_state):
        item=self.requests[request_id]
        if item["state"]!="APPROVED" or item["actionDigest"]!=digest_json(actual_action):
            raise RuntimeError("FIXTURE_DENIED")
        now=datetime.now(UTC)
        unsigned={"schema":"haa.execution-grant.v1","requestId":request_id,
            "executionId":execution_id,"actionDigest":item["actionDigest"],
            "executorAudience":"exec","issuedAt":now.isoformat(),
            "expiresAt":(now+timedelta(seconds=20)).isoformat(),
            "authorityKeyId":"key","signatureAlgorithm":"Ed25519"}
        item["state"]="CONSUMED"
        self.consumed.append(request_id)
        return {**unsigned,"signature":base64.urlsafe_b64encode(
            self.private.sign(canonicalize(unsigned).encode())).decode().rstrip("=")}


from scripts.haa.policy import pin_policy


class ProtectedIntegrationTest(unittest.TestCase):
    def test_signed_task_to_commit_to_separately_signed_plan_close(self):
        self._exercise(batch=False)

    def test_signed_batch_to_commit_to_separately_signed_plan_close(self):
        self._exercise(batch=True)

    def _exercise(self, *, batch):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        base=Path(temp.name).resolve()
        root=base/"repo";root.mkdir()
        state=base/"state";state.mkdir(mode=0o700)
        def git(*args):
            return subprocess.check_output(["git","-C",str(root),*args],
                stderr=subprocess.DEVNULL,text=True).strip()
        git("init","-b","candidate");git("config","user.name","fixture")
        git("config","user.email","fixture@example.invalid")
        git("remote","add","origin","https://github.com/example/workflow-fixture.git")
        (root/"README.md").write_text("before")
        paths=("OTHER.md","README.md") if batch else ("README.md",)
        if batch:
            (root/"OTHER.md").write_text("other")
        (root/"docs").mkdir()
        (root/"docs/p.md").write_text("# Plan")
        (root/"docs/tasks.md").write_text("- [ ] t")
        card=root/"card.json"
        card.write_text(json.dumps({"schema_version":2,"card_id":"t","task_id":"t",
            "spec":"Change README","allowed_paths":list(paths),
            "acceptance_criteria":[{"id":"HP-1","statement":"README candidate"}],
            "verification_commands":[{"id":"check","criterion_ids":["HP-1"],
                                      "argv":["/usr/bin/true"]}],
            "rri":55,"band":"Med-high","plan":"docs/p.md"}))
        git("add",*paths,"docs","card.json");git("commit","-m","base")
        approved=ApprovedPlan("example/workflow-fixture","p","candidate",git("rev-parse","HEAD"),
            "docs/p.md",sha256(b"# Plan").hexdigest(),"docs/tasks.md",
            sha256(b"- [ ] t").hexdigest(),("t",))
        layout=SimpleNamespace(target=root,state=state)
        with patch("scripts.haa.protected_plan_entry.validate_layout"):
            plan=initialize_plan(layout=layout,approved=approved,directory=state,signing_key=b"P"*32)
        journal_dir=state/"admission";journal_dir.mkdir(mode=0o700)
        AdmissionJournal.initialize(journal_dir)
        leases=VolatileLeaseStore(AdmissionJournal(journal_dir))
        self.addCleanup(leases.close)
        checkpoints=CheckpointStore(state/"checkpoints",signing_key=b"C"*32)
        policy_pin=pin_policy(root=root, repository="example/workflow-fixture",
            card_sha256=sha256(card.read_bytes()).hexdigest(),rri=55,requires_haa=True,
            capabilities=("commit","edit","test"),source_paths=("docs/p.md",),plan_close_requires_haa=True)
        task=bind_trusted_task(TrustedTask(root,"example/workflow-fixture",card,"new",
             ("commit","edit","test"),300),card_sha256=sha256(card.read_bytes()).hexdigest(),
             authoritative_rri=55,policy_pin=policy_pin)
        haa=FakeHaa()
        attempt=request_bound_task(task=task,requester=haa,checkpoints=checkpoints)
        self.assertEqual(attempt.status,"WAITING_FOR_HUMAN")
        haa.approve_fixture(attempt.request_id)
        reconcile_status(haa,checkpoints,attempt.attempt_id)
        lease=activate_bound_task(task=task,executor=haa,checkpoints=checkpoints,leases=leases,
                                 attempt_id=attempt.attempt_id,pin=haa.pin)
        authority=RunnerAuthority(scope=RunnerScope(task,lease.lease_id),leases=leases,
                                  existing_boundary=Mock())
        authority.preflight()
        worker_uid=os.geteuid()+1
        broker=WorkerBroker(authority,worker_uid=worker_uid)
        window=broker.dispatch(worker_uid,{"op":"status"})["window"]
        if batch:
            response=broker.dispatch(worker_uid,{"op":"replace_batch","window":window,"changes":[
                {"path":"README.md","before_sha256":sha256(b"before").hexdigest(),"content":"candidate"},
                {"path":"OTHER.md","before_sha256":sha256(b"other").hexdigest(),"content":"second"}]})
            self.assertEqual(response["status"],"BATCH_ACCEPTED")
            self.assertEqual((root/"README.md").read_text(),"before")
            accepted=broker.seal()
        else:
            broker.dispatch(worker_uid,{"op":"replace","window":window,"path":"README.md",
                 "before_sha256":sha256(b"before").hexdigest(),"content":"candidate"})
            accepted=broker.seal()
        verifier=Mock()
        def fixture_verify(candidate,commands):
            # Verification fixture checks the exact Git tree; no claim of
            # isolated real command provenance.
            self.assertEqual(git("show",candidate.tree+":README.md"),"candidate")
            if batch:
                self.assertEqual(git("show",candidate.tree+":OTHER.md"),"second")
                self.assertEqual((root/"README.md").read_text(),"before")
                self.assertEqual((root/"OTHER.md").read_text(),"other")
            self.assertEqual(commands,(("/usr/bin/true",),))
            return VerificationResult(candidate.tree,candidate.session,candidate.commands_digest,
                                      (0,),digest_json({"fixture":"tree checked"}))
        verifier.verify.side_effect=fixture_verify
        adapter=(BatchCommit(authority,state=state,verifier=verifier,proposal=accepted) if batch else
                 ProtectedCommit(authority,state=state,verifier=verifier,accepted_edit=accepted))
        workflow=ProtectedWorkflow(commit_adapter=adapter,plan=plan)
        completion=workflow.complete_task(paths)
        self.assertEqual(plan.read_snapshot().completed_tasks,("t",))
        self.assertEqual(plan.read_snapshot().workflow_state,"ACTIVE")
        self.assertEqual(git("rev-parse","HEAD"),completion["commit"])
        self.assertEqual(git("status","--porcelain"),"")
        with self.assertRaises(LeaseError):
            leases.load(lease.lease_id)
        self.assertEqual(len(haa.consumed),1)
        with patch("scripts.haa.protected_plan_entry.validate_layout"):
            controller=PlanCloseController(layout=layout,approved=approved,journal=plan,
                supervisor_lock=RLock(),assert_no_active_tasks=lambda:None,
                verify_plan=lambda head,s:{"status":"PASS","head":head,
                     "evidenceDigest":digest_json({"fixture":"plan check"})})
        controller.mark_ready()
        close=controller.request_close(haa)
        self.assertNotEqual(close["requestId"],attempt.request_id)
        haa.approve_fixture(close["requestId"])
        result=controller.finalize_close(haa,haa.pin)
        self.assertEqual(result["state"],"PLAN_DONE")
        self.assertEqual(controller.projection()["state"],"PLAN_DONE")
        self.assertEqual(len(haa.consumed),2)
