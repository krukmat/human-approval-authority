from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from scripts.haa.protected_plan_validation import PlanValidation
from scripts.haa.protected_commit import VerificationResult
from scripts.haa.verification_backend import ExactTreeVerifier
from scripts.haa.contracts import digest_json
from scripts.haa.plan_closure import ClosureError


class PlanValidationTest(unittest.TestCase):
    def test_exact_head_and_failed_exit(self):
        verifier=Mock(spec=ExactTreeVerifier);verifier.repo=Path("/fixture")
        head="a"*40;tree="b"*40
        snapshot=SimpleNamespace(plan_id="p",plan_version="v")
        validate=PlanValidation(verifier=verifier,commands=(("/usr/bin/true",),))
        def result(c,cmd):
            self.assertEqual(c.tree,tree)
            return VerificationResult(c.tree,c.session,c.commands_digest,(0,),digest_json({"test":"fixture"}))
        verifier.verify.side_effect=result
        with patch("scripts.haa.protected_plan_validation._git",side_effect=[
                head.encode(),tree.encode(),b"refs/heads/candidate",head.encode()]):
            self.assertEqual(validate(head,snapshot)["status"],"PASS")
        verifier.verify.side_effect=lambda c,cmd:VerificationResult(
            c.tree,c.session,c.commands_digest,(7,),digest_json({"test":"failure"}))
        with patch("scripts.haa.protected_plan_validation._git",side_effect=[
                head.encode(),tree.encode(),b"refs/heads/candidate"]):
            with self.assertRaisesRegex(ClosureError,"VALIDATION_FAILED"):
                validate(head,snapshot)
