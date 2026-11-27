from pathlib import Path
import unittest
from unittest.mock import patch
from scripts.haa.protected_host import HostLayout, HostBoundaryError, validate_layout


class HostBoundaryTest(unittest.TestCase):
    def test_same_uid_and_root_rejected(self):
        for a,b in [(501,501),(0,501),(501,0)]:
            with self.subTest(a=a,b=b), self.assertRaises(HostBoundaryError):
                validate_layout(HostLayout(a,b,Path("/install"),Path("/state"),
                                           Path("/target"),Path("/scratch")), effective_uid=a)

    def test_wrong_effective_identity_rejected(self):
        with self.assertRaises(HostBoundaryError):
            validate_layout(HostLayout(501,502,Path("/install"),Path("/state"),
                                       Path("/target"),Path("/scratch")), effective_uid=502)

    def test_overlapping_roots_rejected(self):
        with patch("scripts.haa.protected_host._check_chain"):
            with self.assertRaisesRegex(HostBoundaryError,"OVERLAPPING"):
                validate_layout(HostLayout(501,502,Path("/install"),Path("/state"),
                                           Path("/state/target"),Path("/scratch")), effective_uid=501)

    def test_dac_pass_is_not_isolation_certificate(self):
        with patch("scripts.haa.protected_host._check_chain"):
            result=validate_layout(HostLayout(501,502,Path("/install"),Path("/state"),
                                              Path("/target"),Path("/scratch")), effective_uid=501)
        self.assertEqual(result["status"],"DAC_PREFLIGHT_PASS")
        self.assertFalse(result["isolation_certified"])
