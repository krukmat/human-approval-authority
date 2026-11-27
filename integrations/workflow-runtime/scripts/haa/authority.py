"""Side-effect-free Workflow authority acquisition.

W2 ends at a detached-verified HAA ExecutionGrant. It deliberately does not
create AuthorityLease state or mutate the Workflow workflow.
"""

from __future__ import annotations

from typing import Any

from scripts.haa.client import HaaExecutorClient, HaaRequesterClient
from scripts.haa.contracts import digest_json
from scripts.haa.grants import verify_execution_grant


class HaaAuthorityError(RuntimeError):
    """The requested exact authority could not be safely acquired."""


def request_exact_action(
    client: HaaRequesterClient,
    action: dict[str, Any],
    *,
    ttl_ms: int = 10 * 60_000,
) -> dict[str, Any]:
    request = client.request_approval(action, ttl_ms=ttl_ms)
    expected_digest = digest_json(action)
    actual_digest = request.get("actionDigest")
    if actual_digest != expected_digest:
        raise HaaAuthorityError("REQUEST_ACTION_DIGEST_MISMATCH")
    intent = request.get("intent")
    if isinstance(intent, dict):
        audience = intent.get("executorAudience")
        if audience is not None and audience != client.config.executor_audience:
            raise HaaAuthorityError("REQUEST_EXECUTOR_AUDIENCE_MISMATCH")
    return request


def authorize_exact_action(
    client: HaaExecutorClient,
    *,
    request_id: str,
    execution_id: str,
    actual_action: dict[str, Any],
    actual_state: dict[str, Any],
) -> dict[str, Any]:
    request = client.get_request(request_id)
    expected_digest = request.get("actionDigest")
    if not isinstance(expected_digest, str) or not expected_digest:
        raise HaaAuthorityError("HAA_INVALID_REQUEST_RESPONSE")
    if digest_json(actual_action) != expected_digest:
        raise HaaAuthorityError("ACTION_DIGEST_MISMATCH")

    intent = request.get("intent")
    if not isinstance(intent, dict):
        raise HaaAuthorityError("HAA_INVALID_REQUEST_RESPONSE")
    if intent.get("executorAudience") != client.config.executor_audience:
        raise HaaAuthorityError("EXECUTOR_AUDIENCE_MISMATCH")

    grant = client.authorize(
        request_id=request_id,
        execution_id=execution_id,
        actual_action=actual_action,
        actual_state=actual_state,
    )
    verify_execution_grant(
        grant=grant,
        authority_keys=client.authority_keys(),
        expected_request_id=request_id,
        expected_execution_id=execution_id,
        expected_action_digest=expected_digest,
        expected_executor_audience=client.config.executor_audience,
    )
    return grant
