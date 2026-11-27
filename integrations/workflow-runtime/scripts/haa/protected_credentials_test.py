import json
from pathlib import Path
from unittest.mock import patch
import unittest
from scripts.haa.protected_credentials import load_clients,CredentialError


class ProtectedCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.req={"base_url":"http://127.0.0.1:8795","api_key":"request-fixture",
                  "approver_principal_id":"human","executor_audience":"exec"}
        self.exe={"base_url":self.req["base_url"],"api_key":"execute-fixture",
                  "executor_audience":"exec"}

    def load(self):
        with patch("scripts.haa.protected_credentials.read_private_file",
                   side_effect=[json.dumps(self.req).encode(),json.dumps(self.exe).encode()]):
            return load_clients(state=Path("/fixture"),executor_uid=471)

    def test_distinct_clients(self):
        req,exe=self.load()
        self.assertEqual(req.config.api_key,"request-fixture")
        self.assertEqual(exe.config.api_key,"execute-fixture")

    def test_same_key_denied(self):
        self.exe["api_key"]=self.req["api_key"]
        with self.assertRaisesRegex(CredentialError,"MISMATCH"):
            self.load()

    def test_remote_plain_http_denied(self):
        self.exe["base_url"]=self.req["base_url"]="http://example.invalid:8795"
        with self.assertRaisesRegex(CredentialError,"ENDPOINT"):
            self.load()

    def test_role_extra_field_denied(self):
        self.exe["approver_principal_id"]="human"
        with self.assertRaisesRegex(CredentialError,"INVALID"):
            self.load()
