"""Session operations: ``/v1/auth/sessions`` (API spec 014 / 006)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .client import ApiClient
from .errors import ApiError

DEVICE_NAME = "EntrePatasETurnos MCP"


class SessionTokens(BaseModel):
    session_id: str
    user_id: str
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def _tokens(body: Any, status: int) -> SessionTokens:
    if not isinstance(body, dict):
        raise ApiError("upstream_invalid_response", "unexpected session response", status)
    try:
        return SessionTokens(
            session_id=str(body["sessionId"]),
            user_id=str(body["userId"]),
            access_token=str(body["accessToken"]),
            access_expires_at=body["accessTokenExpiresAt"],
            refresh_token=str(body["refreshToken"]),
            refresh_expires_at=body["refreshTokenExpiresAt"],
        )
    except (KeyError, ValueError) as exc:
        raise ApiError("upstream_invalid_response", "unexpected session response", status) from exc


async def create_google_session(client: ApiClient, id_token: str) -> SessionTokens:
    body = await client._post(
        "/v1/auth/sessions/google", json={"idToken": id_token, "deviceName": DEVICE_NAME}
    )
    return _tokens(body, 201)


async def refresh_session(client: ApiClient, session_id: str, refresh_token: str) -> SessionTokens:
    body = await client._post(
        f"/v1/auth/sessions/{session_id}/refresh", json={"refreshToken": refresh_token}
    )
    return _tokens(body, 200)


async def delete_session(client: ApiClient, session_id: str, access_token: str) -> None:
    await client._delete(f"/v1/auth/sessions/{session_id}", token=access_token)


async def info(client: ApiClient, timeout: float) -> None:
    """``GET /v1/info`` (public) - used only by the readiness probe."""
    await client._get("/v1/info", timeout=timeout)
