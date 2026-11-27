"""Exact committed HEAD plan-wide verification, independent of task lease."""
from __future__ import annotations
from scripts.haa.contracts import digest_json
from scripts.haa.protected_commit import CandidateTree,VerificationResult
from scripts.haa.protected_plan_entry import _git
from scripts.haa.verification_backend import ExactTreeVerifier
from scripts.haa.plan_closure import ClosureError
import re


class PlanValidation:
    def __init__(self,*,verifier:ExactTreeVerifier,commands:tuple[tuple[str,...],...]):
        if (not isinstance(verifier,ExactTreeVerifier) or not commands
                or not isinstance(commands,tuple)
                or any(not isinstance(c,tuple) or not c or
                       any(not isinstance(a,str) or not a for a in c) for c in commands)):
            raise ClosureError("PINNED_PLAN_COMMANDS_REQUIRED")
        self.verifier=verifier
        self.commands=commands

    def __call__(self,head,snapshot):
        repo=self.verifier.repo
        if _git(repo,"rev-parse","HEAD").decode().strip()!=head:
            raise ClosureError("PLAN_HEAD_CHANGED")
        tree=_git(repo,"rev-parse",head+"^{tree}").decode().strip()
        branch=_git(repo,"symbolic-ref","HEAD").decode().strip()
        commands_digest=digest_json([list(c) for c in self.commands])
        session=digest_json({"plan":snapshot.plan_id,"version":snapshot.plan_version,
                             "head":head,"purpose":"plan-validation"})
        candidate=CandidateTree(head,branch,tree,(),session,commands_digest)
        result=self.verifier.verify(candidate,self.commands)
        if (not isinstance(result,VerificationResult)
                or (result.tree,result.session,result.commands_digest)!=(tree,session,commands_digest)
                or any(type(code) is not int for code in result.exit_codes)
                or result.exit_codes!=(0,)*len(self.commands)
                or not re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}",result.evidence_digest)
                or _git(repo,"rev-parse","HEAD").decode().strip()!=head):
            raise ClosureError("PLAN_VALIDATION_FAILED")
        return {"status":"PASS","head":head,"evidenceDigest":result.evidence_digest}
