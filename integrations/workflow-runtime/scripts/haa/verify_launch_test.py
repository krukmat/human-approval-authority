"""Synthetic child supervision only; does not prove macOS containment."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from scripts.haa.verify_launch import _run_bounded


class HelperSupervisionTest(unittest.TestCase):
    def test_observed_exit(self):
        self.assertEqual(_run_bounded(sys.executable,
            [sys.executable,"-c","raise SystemExit(7)"],dict(os.environ),2),7)

    def test_timeout_stops_ordinary_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/"late"
            code="import time,pathlib,sys; time.sleep(2); pathlib.Path(sys.argv[1]).touch()"
            parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); time.sleep(30)"
            result=_run_bounded(sys.executable,
                [sys.executable,"-c",parent,code,str(marker)],dict(os.environ),0.5)
            self.assertEqual(result,124)
            time.sleep(2.1)
            self.assertFalse(marker.exists(),"ordinary child survived process-group cleanup")

    def test_reserved_exit_not_pass(self):
        self.assertEqual(_run_bounded(sys.executable,
            [sys.executable,"-c","raise SystemExit(124)"],dict(os.environ),2),125)
