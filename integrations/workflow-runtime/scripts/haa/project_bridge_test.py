from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from scripts.haa.project_bridge import local_invocation, BridgeError


class ProjectBridgeTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name).resolve()
        self.scratch=base/"scratch";self.scratch.mkdir()
        self.packet=base/"packet";self.packet.write_text("synthetic")
        self.output=base/"output"
        self.fenix=base/"delegate-low-rri.py";self.fenix.touch()
        self.dubbridge=base/"run_local_task.py";self.dubbridge.touch()
        self.args=dict(repository="krukmat/fenix",rri=25,task_id="t",paths=("src/a.py","src/b.py"),
            python=Path(sys.executable).resolve(),scratch=self.scratch,runner=self.fenix,
            input_file=self.packet,output_file=self.output)

    def test_fenix_low_preserves_native_cli_and_no_hidden_model_selection(self):
        v=local_invocation(**self.args,dry_run=True)
        self.assertIn("--dry-run",v.argv)
        self.assertIn("--apply",v.argv)
        self.assertEqual(v.argv.count("--allow-path"),2)
        self.assertNotIn("--model",v.argv)
        self.assertEqual(v.cwd,self.scratch)

    def test_fenix_high_does_not_route_local(self):
        with self.assertRaisesRegex(BridgeError,"HIGH_BAND"):
            local_invocation(**{**self.args,"rri":26})

    def test_dubbridge_native_card_cli(self):
        v=local_invocation(**{**self.args,"repository":"krukmat/dubbridge",
                              "runner":self.dubbridge,"rri":35})
        self.assertEqual(v.argv[3:],("--card",str(self.packet),"--worktree",str(self.scratch),
                                     "--out",str(self.output)))

    def test_no_unknown_project_or_unsafe_scope(self):
        for update in ({"repository":"unknown/project"},{"paths":("../escape",)},
                       {"paths":("a.py","a.py")},{"output_file":self.scratch/"out"}):
            with self.subTest(update=update),self.assertRaises(BridgeError):
                local_invocation(**{**self.args,**update})
