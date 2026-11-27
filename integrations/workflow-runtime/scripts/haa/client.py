"""Public-HTTP HAA clients for the Workflow software-factory adapter.

Requester and executor credentials are intentionally split into separate config
types and constructors. This module never performs a Workflow workflow side effect.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 10.0


class HaaClientError(RuntimeError):
    """Fail-closed HAA transport or response error."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HaaClientError(f"MISSING_HAA_CONFIGURATION:{name}")
    return value


@dataclass(frozen=True)
class RequesterConfig:
    base_url: str
    api_key: str
    approver_principal_id: str
    executor_audience: str

    @classmethod
    def from_env(cls) -> "RequesterConfig":
        return cls(
            base_url=_required_env("HAA_BASE_URL"),
            api_key=_required_env("HAA_REQUESTER_API_KEY"),
            approver_principal_id=_required_env("HAA_APPROVER_PRINCIPAL_ID"),
            executor_audience=_required_env("HAA_EXECUTOR_AUDIENCE"),
        )


@dataclass(frozen=True)
class ExecutorConfig:
    base_url: str
    api_key: str
    executor_audience: str

    @classmethod
    def from_env(cls) -> "ExecutorConfig":
        return cls(
            base_url=_required_env("HAA_BASE_URL"),
            api_key=_required_env("HAA_EXECUTOR_API_KEY"),
            executor_audience=_required_env("HAA_EXECUTOR_AUDIENCE"),
        )


class _HttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url or not api_key:
            raise HaaClientError("INVALID_HAA_CLIENT_CONFIGURATION")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._opener = opener
        self._timeout_seconds = timeout_seconds

    def _call(self, path: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"x-api-key": self._api_key, "accept": "application/json"}
        if encoded is not None:
            headers["content-type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=encoded,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                code = parsed.get("error", detail) if isinstance(parsed, dict) else detail
            except json.JSONDecodeError:
                code = detail
            raise HaaClientError(f"HAA_HTTP_{exc.code}:{code}") from exc
        except URLError as exc:
            raise HaaClientError(f"HAA_UNREACHABLE:{exc.reason}") from exc
        except OSError as exc:
            raise HaaClientError(f"HAA_TRANSPORT_ERROR:{exc}") from exc

        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HaaClientError("HAA_INVALID_JSON_RESPONSE") from exc


class HaaRequesterClient(_HttpClient):
    def __init__(
        self,
        config: RequesterConfig,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            config.base_url,
            config.api_key,
            opener=opener,
            timeout_seconds=timeout_seconds,
        )
        self.config = config

    def request_approval(
        self,
        action: dict[str, Any],
        *,
        ttl_ms: int = 10 * 60_000,
    ) -> dict[str, Any]:
        if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or ttl_ms <= 0:
            raise HaaClientError("INVALID_APPROVAL_TTL")
        result = self._call(
            "/v1/approval-requests",
            method="POST",
            body={
                "action": action,
                "approverPrincipalId": self.config.approver_principal_id,
                "executorAudience": self.config.executor_audience,
                "ttlMs": ttl_ms,
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            raise HaaClientError("HAA_INVALID_REQUEST_RESPONSE")
        return result

    def get_request(self, request_id: str) -> dict[str, Any]:
        if not request_id:
            raise HaaClientError("INVALID_REQUEST_ID")
        result = self._call(f"/v1/approval-requests/{quote(request_id, safe='')}")
        if not isinstance(result, dict) or result.get("id") != request_id:
            raise HaaClientError("HAA_INVALID_REQUEST_RESPONSE")
        return result


class HaaExecutorClient(_HttpClient):
    def __init__(
        self,
        config: ExecutorConfig,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            config.base_url,
            config.api_key,
            opener=opener,
            timeout_seconds=timeout_seconds,
        )
        self.config = config

    def get_request(self, request_id: str) -> dict[str, Any]:
        if not request_id:
            raise HaaClientError("INVALID_REQUEST_ID")
        result = self._call(f"/v1/approval-requests/{quote(request_id, safe='')}")
        if not isinstance(result, dict) or result.get("id") != request_id:
            raise HaaClientError("HAA_INVALID_REQUEST_RESPONSE")
        return result

    def authorize(
        self,
        *,
        request_id: str,
        execution_id: str,
        actual_action: dict[str, Any],
        actual_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not request_id or not execution_id:
            raise HaaClientError("INVALID_AUTHORIZATION_ID")
        result = self._call(
            f"/v1/approval-requests/{quote(request_id, safe='')}/authorize",
            method="POST",
            body={
                "executionId": execution_id,
                "actualAction": actual_action,
                "actualState": actual_state,
            },
        )
        if not isinstance(result, dict):
            raise HaaClientError("HAA_INVALID_GRANT_RESPONSE")
        return result

    def authority_keys(self) -> list[dict[str, Any]]:
        result = self._call("/v1/authority-keys")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise HaaClientError("HAA_INVALID_AUTHORITY_KEYS_RESPONSE")
        return result
