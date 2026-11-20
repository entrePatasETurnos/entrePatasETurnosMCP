"""HTTP client for the EntrePatasETurnos API (research R5).

There is deliberately no public "make any request" method: each API operation the server is
allowed to call has its own typed function in a sibling module (``pets``, ``bookings``, ...).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from .errors import ApiError, OutcomeUnknown, UpstreamTimeout, UpstreamUnavailable

logger = logging.getLogger(__name__)

Params = dict[str, str | int | float | None]
_KNOWN_ERROR_KEYS = {"error", "message", "fields", "_links"}


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(connect=3.0, read=timeout_seconds, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=20),
            headers={"Accept": "application/json", "User-Agent": "entrepataseturnos-mcp"},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ----------------------------------------------------------------- verbs (package-private)

    async def _get(
        self,
        path: str,
        *,
        token: str | None = None,
        params: Params | None = None,
        timeout: float | None = None,
    ) -> Any:
        return await self._request("GET", path, token=token, params=params, timeout=timeout)

    async def _post(self, path: str, *, token: str | None = None, json: Any = None) -> Any:
        return await self._request("POST", path, token=token, json=json)

    async def _put(self, path: str, *, token: str | None = None, json: Any = None) -> Any:
        return await self._request("PUT", path, token=token, json=json)

    async def _delete(self, path: str, *, token: str | None = None) -> Any:
        return await self._request("DELETE", path, token=token)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        params: Params | None = None,
        json: Any = None,
        timeout: float | None = None,
    ) -> Any:
        if not path.startswith("/v1/"):
            raise AssertionError(f"API paths must use versioned /v1/ routes, got {path!r}")
        is_write = method != "GET"
        headers = {"X-Correlation-Id": str(uuid.uuid4())}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None} or None
        extra: dict[str, Any] = {}
        if timeout is not None:
            extra["timeout"] = timeout

        attempts = 1 if is_write else 2  # GET: one retry on connection failure only
        started = time.monotonic()
        response: httpx.Response | None = None
        for attempt in range(attempts):
            try:
                response = await self._http.request(
                    method, path, params=clean_params, json=json, headers=headers, **extra
                )
                break
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # The request never reached the API, so a retry (GET only) is safe.
                if attempt + 1 < attempts:
                    continue
                self._log(method, path, None, started, "unreachable")
                raise UpstreamUnavailable("the API could not be reached") from None
            except httpx.TimeoutException:
                self._log(method, path, None, started, "timeout")
                if is_write:
                    raise OutcomeUnknown("the API did not answer in time") from None
                raise UpstreamTimeout("the API did not answer in time") from None
            except httpx.TransportError:
                # The connection broke after the request may have been sent.
                self._log(method, path, None, started, "transport_error")
                if is_write:
                    raise OutcomeUnknown("the connection to the API was interrupted") from None
                raise UpstreamUnavailable("the API could not be reached") from None
        assert response is not None
        self._log(method, path, response.status_code, started, None)
        return self._parse(response)

    # --------------------------------------------------------------------------- helpers

    @staticmethod
    def _log(method: str, path: str, status: int | None, started: float, failure: str | None) -> None:
        logger.info(
            "api call",
            extra={
                "api_method": method,
                "api_path": path,
                "api_status": status,
                "api_failure": failure,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        status = response.status_code
        if 200 <= status < 300:
            if status == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                raise ApiError(
                    "upstream_invalid_response", "the API returned an unreadable response", status
                ) from None
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("error"), str):
            if status >= 500:
                raise ApiError(
                    "upstream_unavailable", "the API is unavailable; try again later", status
                )
            if status == 401:
                raise ApiError("unauthorized", "authentication required", status)
            raise ApiError(
                "upstream_invalid_response", "the API returned an unexpected error", status
            )
        fields = body.get("fields")
        extras = {k: v for k, v in body.items() if k not in _KNOWN_ERROR_KEYS}
        raise ApiError(
            body["error"],
            str(body.get("message") or body["error"]),
            status,
            fields={str(k): str(v) for k, v in fields.items()} if isinstance(fields, dict) else None,
            extras=extras,
        )
