import unittest
from scripts.haa.compare_workflow import compare, EvidenceError


class CompareWorkflowTest(unittest.TestCase):
    def pair(self):
        a={"schema":"workflow.ab.observed.v1","status":"PASS","pair_id":"p",
           "provenance":"OBSERVED_MATCHED_REPLAY","variant":"baseline","base_commit":"a"*40,
           "task_digest":"t","implementation_digest":"i","checks_digest":"c",
           "model_calls":1,"tokens":20,"reviewer_calls":1,"human_prompts":0,
           "authorized_haa_prompts":0,"wall_ms":100,"cpu_ms":10,"peak_rss_bytes":1000}
        b={**a,"variant":"haa","wall_ms":110,"cpu_ms":12,"peak_rss_bytes":1100,
           "human_prompts":1,"authorized_haa_prompts":1}
        return a,b

    def test_matched_pair_deltas_and_allowed_prompt(self):
        result=compare(self.pair())
        self.assertEqual(result["status"],"MEASURED_NO_ADDITIONAL_MODEL_OVERHEAD")
        self.assertEqual(result["deltas"]["wall_ms"]["p95"],10)
        self.assertEqual(result["activation"],"NO_GO")

    def test_missing_and_unmatched_evidence_rejected(self):
        a,b=self.pair()
        for data in ([a],[],[a,{**b,"task_digest":"drift"}],
                     [a,{**b,"tokens":None}],[a,b,b]):
            with self.subTest(data=data),self.assertRaises(EvidenceError):
                compare(data)

    def test_added_model_reviewer_or_unapproved_prompt_fails(self):
        a,b=self.pair()
        for patch in ({"model_calls":2},{"tokens":21},{"reviewer_calls":2},{"human_prompts":2}):
            with self.subTest(patch=patch):
                self.assertEqual(compare([a,{**b,**patch}])["status"],"FAIL_GOVERNANCE_OVERHEAD")
