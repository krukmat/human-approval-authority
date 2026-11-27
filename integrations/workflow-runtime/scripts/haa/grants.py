"""Detached HAA ExecutionGrant verification for Workflow.

Semantics are intentionally aligned with HAA's public TypeScript SDK and the
independently validated Python W9 reference executor in verifiable-event-ledger.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from scripts.haa.contracts import canonicalize

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by dependency-missing gate
    InvalidSignature = Exception  # type: ignore[assignment]
    hashes = serialization = ec = ed25519 = None  # type: ignore[assignment]
    _CRYPTOGRAPHY_AVAILABLE = False

DEFAULT_MAX_GRANT_TTL_MS = 30_000
DEFAULT_CLOCK_SKEW_MS = 5_000
GRANT_KEYS = {
    "schema",
    "requestId",
    "executionId",
    "actionDigest",
    "executorAudience",
    "issuedAt",
    "expiresAt",
    "authorityKeyId",
    "signatureAlgorithm",
    "signature",
}


class HaaGrantVerificationError(RuntimeError):
    """A detached grant is unusable for live authority."""


def _parse_iso8601(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise HaaGrantVerificationError(code)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HaaGrantVerificationError(code) from exc
    if parsed.tzinfo is None:
        raise HaaGrantVerificationError(code)
    return parsed.astimezone(UTC)


def _decode_base64url(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise HaaGrantVerificationError("INVALID_GRANT_SIGNATURE") from exc


def verify_execution_grant(
    *,
    grant: dict[str, Any],
    authority_keys: list[dict[str, Any]],
    expected_request_id: str,
    expected_execution_id: str,
    expected_action_digest: str,
    expected_executor_audience: str,
    now: datetime | None = None,
    max_ttl_ms: int = DEFAULT_MAX_GRANT_TTL_MS,
    clock_skew_ms: int = DEFAULT_CLOCK_SKEW_MS,
) -> dict[str, Any]:
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise HaaGrantVerificationError("CRYPTOGRAPHY_DEPENDENCY_MISSING")

    if set(grant) != GRANT_KEYS or any(
        not isinstance(grant.get(key), str) or not grant[key]
        for key in GRANT_KEYS - {"schema", "signatureAlgorithm"}
    ):
        raise HaaGrantVerificationError("INVALID_GRANT_SHAPE")
    if grant.get("schema") != "haa.execution-grant.v1":
        raise HaaGrantVerificationError("UNSUPPORTED_GRANT_SCHEMA")
    algorithm = grant.get("signatureAlgorithm")
    if algorithm not in {"Ed25519", "ES256"}:
        raise HaaGrantVerificationError("UNSUPPORTED_SIGNATURE_ALGORITHM")

    authority = next(
        (item for item in authority_keys if item.get("keyId") == grant["authorityKeyId"]),
        None,
    )
    if authority is None:
        raise HaaGrantVerificationError("UNKNOWN_AUTHORITY_KEY")
    if authority.get("status") != "ACTIVE":
        raise HaaGrantVerificationError("AUTHORITY_KEY_NOT_ACTIVE")
    if authority.get("algorithm") != algorithm:
        raise HaaGrantVerificationError("AUTHORITY_ALGORITHM_MISMATCH")
    public_key_pem = authority.get("publicKeyPem")
    if not isinstance(public_key_pem, str) or not public_key_pem:
        raise HaaGrantVerificationError("AUTHORITY_KEY_METADATA_INVALID")

    issued_at = _parse_iso8601(grant["issuedAt"], "GRANT_INVALID_TIME_RANGE")
    expires_at = _parse_iso8601(grant["expiresAt"], "GRANT_INVALID_TIME_RANGE")
    if expires_at <= issued_at:
        raise HaaGrantVerificationError("GRANT_INVALID_TIME_RANGE")
    if (
        isinstance(max_ttl_ms, bool)
        or not isinstance(max_ttl_ms, int)
        or max_ttl_ms <= 0
        or isinstance(clock_skew_ms, bool)
        or not isinstance(clock_skew_ms, int)
        or clock_skew_ms < 0
    ):
        raise HaaGrantVerificationError("INVALID_GRANT_SHAPE")

    current = (now or datetime.now(UTC)).astimezone(UTC)
    if issued_at.timestamp() * 1000 > current.timestamp() * 1000 + clock_skew_ms:
        raise HaaGrantVerificationError("GRANT_ISSUED_IN_FUTURE")
    if (expires_at - issued_at).total_seconds() * 1000 > max_ttl_ms:
        raise HaaGrantVerificationError("GRANT_TTL_EXCEEDS_POLICY")
    if expires_at <= current:
        raise HaaGrantVerificationError("GRANT_EXPIRED")

    if authority.get("createdAt") is not None:
        created_at = _parse_iso8601(
            authority["createdAt"],
            "AUTHORITY_KEY_METADATA_INVALID",
        )
        if issued_at.timestamp() * 1000 + clock_skew_ms < created_at.timestamp() * 1000:
            raise HaaGrantVerificationError("GRANT_ISSUED_BEFORE_KEY_ACTIVE")

    unsigned = {
        "schema": grant["schema"],
        "requestId": grant["requestId"],
        "executionId": grant["executionId"],
        "actionDigest": grant["actionDigest"],
        "executorAudience": grant["executorAudience"],
        "issuedAt": grant["issuedAt"],
        "expiresAt": grant["expiresAt"],
        "authorityKeyId": grant["authorityKeyId"],
        "signatureAlgorithm": grant["signatureAlgorithm"],
    }
    signed_bytes = canonicalize(unsigned).encode("utf-8")
    signature = _decode_base64url(grant["signature"])
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if algorithm == "Ed25519":
            if not isinstance(public_key, ed25519.Ed25519PublicKey):
                raise HaaGrantVerificationError("AUTHORITY_ALGORITHM_MISMATCH")
            public_key.verify(signature, signed_bytes)
        else:
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                raise HaaGrantVerificationError("AUTHORITY_ALGORITHM_MISMATCH")
            public_key.verify(signature, signed_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise HaaGrantVerificationError("INVALID_GRANT_SIGNATURE") from exc
    except HaaGrantVerificationError:
        raise
    except (ValueError, TypeError) as exc:
        raise HaaGrantVerificationError("AUTHORITY_KEY_METADATA_INVALID") from exc

    bindings = (
        (grant["requestId"], expected_request_id, "REQUEST_ID_MISMATCH"),
        (grant["executionId"], expected_execution_id, "EXECUTION_ID_MISMATCH"),
        (grant["actionDigest"], expected_action_digest, "ACTION_DIGEST_MISMATCH"),
        (
            grant["executorAudience"],
            expected_executor_audience,
            "EXECUTOR_AUDIENCE_MISMATCH",
        ),
    )
    for actual, expected, code in bindings:
        if actual != expected:
            raise HaaGrantVerificationError(code)
    return grant
