from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import unittest

from scripts.haa import grants
from scripts.haa.contracts import canonicalize
from scripts.haa.grants import HaaGrantVerificationError, verify_execution_grant


@unittest.skipUnless(grants._CRYPTOGRAPHY_AVAILABLE, "cryptography dependency not installed")
class GrantVerificationTest(unittest.TestCase):
    def signed(self):
        private_key = grants.ed25519.Ed25519PrivateKey.generate()
        public_pem = private_key.public_key().public_bytes(
            grants.serialization.Encoding.PEM,
            grants.serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)
        unsigned = {
            "schema": "haa.execution-grant.v1",
            "requestId": "req-1",
            "executionId": "exec-1",
            "actionDigest": "sha256:approved",
            "executorAudience": "dubbridge-executor",
            "issuedAt": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "expiresAt": (now + timedelta(seconds=30)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "authorityKeyId": "authority-1",
            "signatureAlgorithm": "Ed25519",
        }
        signature = private_key.sign(canonicalize(unsigned).encode())
        grant = {
            **unsigned,
            "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
        }
        keys = [{
            "keyId": "authority-1",
            "algorithm": "Ed25519",
            "publicKeyPem": public_pem,
            "status": "ACTIVE",
            "createdAt": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        }]
        return now, grant, keys

    def test_exact_active_grant_verifies(self):
        now, grant, keys = self.signed()
        self.assertIs(
            verify_execution_grant(
                grant=grant,
                authority_keys=keys,
                expected_request_id="req-1",
                expected_execution_id="exec-1",
                expected_action_digest="sha256:approved",
                expected_executor_audience="dubbridge-executor",
                now=now + timedelta(seconds=1),
            ),
            grant,
        )

    def test_retired_key_and_binding_mismatch_fail_closed(self):
        now, grant, keys = self.signed()
        keys[0]["status"] = "RETIRED"
        with self.assertRaisesRegex(HaaGrantVerificationError, "AUTHORITY_KEY_NOT_ACTIVE"):
            verify_execution_grant(
                grant=grant,
                authority_keys=keys,
                expected_request_id="req-1",
                expected_execution_id="exec-1",
                expected_action_digest="sha256:approved",
                expected_executor_audience="dubbridge-executor",
                now=now,
            )

        now, grant, keys = self.signed()
        with self.assertRaisesRegex(HaaGrantVerificationError, "EXECUTOR_AUDIENCE_MISMATCH"):
            verify_execution_grant(
                grant=grant,
                authority_keys=keys,
                expected_request_id="req-1",
                expected_execution_id="exec-1",
                expected_action_digest="sha256:approved",
                expected_executor_audience="wrong",
                now=now,
            )


class DependencyGateTest(unittest.TestCase):
    def test_missing_crypto_dependency_fails_closed(self):
        if grants._CRYPTOGRAPHY_AVAILABLE:
            self.skipTest("dependency installed")
        with self.assertRaisesRegex(HaaGrantVerificationError, "CRYPTOGRAPHY_DEPENDENCY_MISSING"):
            verify_execution_grant(
                grant={},
                authority_keys=[],
                expected_request_id="r",
                expected_execution_id="e",
                expected_action_digest="d",
                expected_executor_audience="a",
            )


if __name__ == "__main__":
    unittest.main()
