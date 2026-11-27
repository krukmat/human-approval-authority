from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock,patch
import os
import json
import unittest

from scripts.haa.verification_backend import VerificationError,VerificationIdentity
from scripts.haa.macos_verifier_launcher import MacOSVerifierLauncher,_idle


class MacOSLauncherTest(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.state=Path(t.name).resolve()
        self.exports=self.state/"exports";self.exports.mkdir()
        self.source=self.exports/"verify-fixture";self.source.mkdir(mode=0o750)
        self.source.chmod(0o750)
        self.identity=VerificationIdentity(os.geteuid(),os.geteuid()+1,os.geteuid()+2,
                                           self.source.stat().st_gid)
        for target,kwargs in [
            ("scripts.haa.macos_verifier_launcher.platform.system",{"return_value":"Darwin"}),
            ("scripts.haa.verification_backend.VerificationIdentity.check",{}),
            ("scripts.haa.macos_verifier_launcher.EXPORTS",{"new":self.exports}),
            ("scripts.haa.macos_verifier_launcher._root_owned",{}),
        ]:
            p=patch(target,**kwargs);p.start();self.addCleanup(p.stop)
        self.launcher=MacOSVerifierLauncher(state=self.state,identity=self.identity)

    def run_fixture(self):
        return self.launcher.run(("/usr/bin/true",),source=self.source,
                                 identity=self.identity,timeout=10)

    def test_direct_exit_and_fixed_sudo_target(self):
        with patch("scripts.haa.macos_verifier_launcher._root_owned") as owned, \
             patch("scripts.haa.macos_verifier_launcher._idle") as idle, \
             patch("scripts.haa.macos_verifier_launcher.subprocess.run",
                   return_value=SimpleNamespace(returncode=7)) as run:
            self.assertEqual(self.run_fixture(),7)
            self.assertFalse(self.launcher.marker.exists())
            self.assertEqual(idle.call_count,2)
            self.assertIn(Path("/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14"),[call.args[0] for call in owned.call_args_list])
            args=run.call_args.args[0]
            self.assertEqual(args[:7],["/usr/bin/sudo","-n","-u",
                f"#{self.identity.verifier_uid}","-g",f"#{self.identity.verifier_gid}","--"])
            self.assertEqual(args[7],"/Library/WorkflowHAA/bin/verify-launch")
            self.assertEqual(len(args),8)
            self.assertEqual(run.call_args.kwargs["timeout"],25)
            payload=json.loads(run.call_args.kwargs["input"])
            self.assertEqual(payload["schema"],"workflow.verifier-launch.v2")
            self.assertEqual(payload["timeout_seconds"],10)

    def test_internal_timeout_quarantined_even_if_uid_idle(self):
        with patch("scripts.haa.macos_verifier_launcher._idle"), \
             patch("scripts.haa.macos_verifier_launcher.subprocess.run",
                   return_value=SimpleNamespace(returncode=124)):
            with self.assertRaisesRegex(VerificationError,"AMBIGUOUS"):
                self.run_fixture()
            self.assertTrue(self.launcher.marker.exists())

    def test_helper_failure_quarantined(self):
        with patch("scripts.haa.macos_verifier_launcher._idle"), \
             patch("scripts.haa.macos_verifier_launcher.subprocess.run",
                   return_value=SimpleNamespace(returncode=125)):
            with self.assertRaisesRegex(VerificationError,"AMBIGUOUS"):
                self.run_fixture()
            self.assertTrue(self.launcher.marker.exists())

    def test_timeout_retains_durable_quarantine(self):
        with patch("scripts.haa.macos_verifier_launcher._idle"), \
             patch("scripts.haa.macos_verifier_launcher.subprocess.run",side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                self.run_fixture()
            self.assertTrue(self.launcher.marker.exists())
            fresh=MacOSVerifierLauncher(state=self.state,identity=self.identity)
            with self.assertRaisesRegex(VerificationError,"QUARANTINED"):
                fresh.run(("/usr/bin/true",),source=self.source,identity=self.identity,timeout=10)

    def test_residual_process_blocks_after_exit(self):
        with patch("scripts.haa.macos_verifier_launcher._idle",
                   side_effect=[None,VerificationError("VERIFIER_PROCESS_RESIDUAL")]), \
             patch("scripts.haa.macos_verifier_launcher.subprocess.run",
                   return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(VerificationError,"RESIDUAL"):
                self.run_fixture()
            self.assertTrue(self.launcher.marker.exists())

    def test_process_table_checks_both_identities(self):
        with patch("scripts.haa.macos_verifier_launcher.subprocess.run",
                   return_value=SimpleNamespace(returncode=0,stdout="999 502 42\n")):
            with self.assertRaisesRegex(VerificationError,"RESIDUAL"):
                _idle(502)
