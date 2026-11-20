"""T028: /oauth/google/callback."""

import json

import httpx
import pytest

from entrepataseturnos_mcp.auth.google import GOOGLE_TOKEN_URL
from entrepataseturnos_mcp.auth.store import PREFIX
from tests.auth.oauth_helpers import (
    CLIENT_REDIRECT,
    http,
    mock_google_and_api,
    query,
    register_client,
    start_authorize,
)

pytestmark = pytest.mark.anyio


async def _callback(app, **params):
    async with http(app) as client:
        client_id = await register_client(client)
        url, _ = await start_authorize(client, client_id)
        params.setdefault("state", query(url)["state"])
        return await client.get("/oauth/google/callback", params=params)


async def _session_keys(redis):
    return [k for k in await redis.keys(PREFIX + "session:*") if b":lock" not in k and b":tokens" not in k]


async def test_success_creates_encrypted_session_and_redirects_with_code(app, respx_mock, redis):
    google, api = mock_google_and_api(respx_mock)
    r = await _callback(app, code="google-code")
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith(CLIENT_REDIRECT)
    q = query(loc)
    assert q["code"] and q["state"] == "client-state"
    assert api.call_count == 1
    assert json.loads(api.calls.last.request.content) == {
        "idToken": "google-id-token",
        "deviceName": "EntrePatasETurnos MCP",
    }
    sent = google.calls.last.request.content.decode()
    assert "code_verifier=" in sent and "client_secret=" in sent
    keys = await _session_keys(redis)
    assert len(keys) == 1
    assert b"api-at-1" not in await redis.get(keys[0])


@pytest.mark.parametrize(
    ("status", "code", "oauth_error"),
    [
        (409, "account_link_required", "access_denied"),
        (403, "account_unavailable", "access_denied"),
        (401, "invalid_assertion", "access_denied"),
        (503, "provider_unavailable", "server_error"),
    ],
)
async def test_api_errors_redirect_with_error_and_no_session(app, respx_mock, redis, status, code, oauth_error):
    mock_google_and_api(respx_mock, api_status=status, api_json={"error": code, "message": "msg"})
    r = await _callback(app, code="google-code")
    assert r.status_code == 302
    q = query(r.headers["location"])
    assert q["error"] == oauth_error and code in q["error_description"]
    assert q["state"] == "client-state" and "code" not in q
    assert await _session_keys(redis) == []


async def test_unknown_or_reused_state_is_400(app, respx_mock):
    mock_google_and_api(respx_mock)
    r = await _callback(app, state="never-issued", code="c")
    assert r.status_code == 400
    async with http(app) as client:
        client_id = await register_client(client)
        url, _ = await start_authorize(client, client_id)
        state = query(url)["state"]
        assert (await client.get("/oauth/google/callback", params={"state": state, "code": "c"})).status_code == 302
        again = await client.get("/oauth/google/callback", params={"state": state, "code": "c"})
    assert again.status_code == 400


async def test_google_exchange_failure(app, respx_mock, redis):
    respx_mock.post(GOOGLE_TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    r = await _callback(app, code="bad")
    assert query(r.headers["location"])["error"] == "server_error"
    assert await _session_keys(redis) == []


async def test_user_cancelled_at_google(app, respx_mock):
    r = await _callback(app, error="access_denied")
    assert query(r.headers["location"])["error"] == "access_denied"
