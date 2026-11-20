"""Drive the OAuth flow over HTTP against the app (Google and the API are mocked with respx)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
import respx
from starlette.applications import Starlette

from entrepataseturnos_mcp.auth.google import GOOGLE_TOKEN_URL, pkce_pair
from tests.conftest import API, PUBLIC

CLIENT_REDIRECT = "http://localhost:9999/callback"


def http(app: Starlette) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=PUBLIC)


def session_body(access: str = "api-at-1", refresh: str = "api-rt-1", user_id: int = 42) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sessionId": 900,
        "accessToken": access,
        "accessTokenExpiresAt": (now + timedelta(minutes=15)).isoformat(),
        "expiresIn": 900,
        "refreshToken": refresh,
        "refreshTokenExpiresAt": (now + timedelta(days=30)).isoformat(),
        "userId": user_id,
        "userEmail": "owner@example.com",
        "userName": "Owner",
        "deviceName": "EntrePatasETurnos MCP",
        "_links": {},
    }


def query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def register_client(client: httpx2.AsyncClient) -> str:
    r = await client.post(
        "/register",
        json={
            "redirect_uris": [CLIENT_REDIRECT],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "client_name": "test client",
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["client_id"])


async def start_authorize(client: httpx2.AsyncClient, client_id: str) -> tuple[str, str]:
    """Returns (google_redirect_url, client_code_verifier)."""
    verifier, challenge = pkce_pair()
    r = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CLIENT_REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "client-state",
        },
    )
    assert r.status_code == 302, r.text
    return r.headers["location"], verifier


def mock_google_and_api(router: respx.MockRouter, *, api_status: int = 201, api_json: Any = None) -> tuple[respx.Route, respx.Route]:
    google = router.post(GOOGLE_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"id_token": "google-id-token", "access_token": "g-at"})
    )
    api = router.post(f"{API}/v1/auth/sessions/google").mock(
        return_value=httpx.Response(api_status, json=api_json if api_json is not None else session_body())
    )
    return google, api


async def sign_in(app: Starlette, router: respx.MockRouter) -> dict[str, Any]:
    """Full flow; returns the /token response JSON."""
    mock_google_and_api(router)
    async with http(app) as client:
        client_id = await register_client(client)
        google_url, verifier = await start_authorize(client, client_id)
        state = query(google_url)["state"]
        cb = await client.get("/oauth/google/callback", params={"state": state, "code": "google-code"})
        assert cb.status_code == 302, cb.text
        code = query(cb.headers["location"])["code"]
        tok = await client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CLIENT_REDIRECT,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        return {**tok.json(), "client_id": client_id}
