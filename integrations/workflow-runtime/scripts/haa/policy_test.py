import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.haa.policy import pin_policy, pin_project_policy, PolicyError

class PolicyTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        (self.root/'policy.md').write_text('v1')
        self.args=dict(root=self.root, repository='example/project', card_sha256='a'*64,
                       rri=10, requires_haa=True, capabilities=('edit','test'),
                       source_paths=('policy.md',), plan_close_requires_haa=False)
    def test_explicit_decision_not_threshold(self):
        p=pin_policy(**self.args)
        self.assertTrue(p.requires_haa)
        other=pin_policy(**{**self.args,'requires_haa':False})
        self.assertNotEqual(p.digest(),other.digest())
        self.assertFalse(other.plan_close_requires_haa)
    def test_policy_drift_denies(self):
        p=pin_policy(**self.args)
        (self.root/'policy.md').write_text('v2')
        with self.assertRaisesRegex(PolicyError,'POLICY_SOURCE_CHANGED'):
            p.validate(root=self.root,repository='example/project',card_sha256='a'*64,rri=10,capabilities=('edit','test'))
    def test_reject_unsupported_and_unknown(self):
        for patch in [{'capabilities':('deploy',)}, {'requires_haa':1}, {'source_paths':('../escape',)}, {'source_paths':()}]:
            with self.assertRaises(PolicyError): pin_policy(**{**self.args,**patch})
        with self.assertRaisesRegex(PolicyError,'UNKNOWN_PROJECT_POLICY'):
            pin_project_policy(**{k:v for k,v in self.args.items() if k!='source_paths'})
    def test_symlink_denied(self):
        (self.root/'alias').symlink_to(self.root/'policy.md')
        with self.assertRaisesRegex(PolicyError,'UNSAFE_POLICY_SOURCE'):
            pin_policy(**{**self.args,'source_paths':('alias',)})

if __name__=='__main__': unittest.main()
