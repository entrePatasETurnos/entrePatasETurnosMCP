"""T027: authorization-server behaviour of RedisOAuthProvider over HTTP."""

import json

import httpx
import pytest

from entrepataseturnos_mcp.auth.crypto import hash_token
from entrepataseturnos_mcp.auth.store import PREFIX
from tests.auth.oauth_helpers import (
    CLIENT_REDIRECT,
    http,
    query,
    register_client,
    sign_in,
    start_authorize,
)
from tests.conftest import API, PUBLIC, mcp_client, result_payload

pytestmark = pytest.mark.anyio


async def test_registration_stores_client(app, components):
    async with http(app) as client:
        client_id = await register_client(client)
    assert await components.provider.get_client(client_id) is not None


async def test_authorize_redirects_to_google_with_pkce_and_stores_pending(app, components, redis):
    async with http(app) as client:
        client_id = await register_client(client)
        url, _ = await start_authorize(client, client_id)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    q = query(url)
    assert q["client_id"] == "google-client-id"
    assert q["redirect_uri"] == f"{PUBLIC}/oauth/google/callback"
    assert q["scope"] == "openid email profile"
    assert q["code_challenge_method"] == "S256" and q["code_challenge"]
    key = PREFIX + "pending:" + hash_token(q["state"])
    assert 0 < await redis.ttl(key) <= 600
    assert q["state"] != "client-state"  # our own state, not the client's


async def test_authorize_rejects_foreign_resource(app):
    async with http(app) as client:
        client_id = await register_client(client)
        r = await client.get(
            "/authorize",
            params={
                "response_type": "code", "client_id": client_id, "redirect_uri": CLIENT_REDIRECT,
                "code_challenge": "x" * 43, "code_challenge_method": "S256", "state": "s",
                "resource": "https://evil.example.com/mcp",
            },
        )
    assert r.status_code == 302 and query(r.headers["location"])["error"] == "invalid_target"


async def test_full_flow_issues_opaque_tokens_stored_only_as_hashes(app, respx_mock, redis):
    tokens = await sign_in(app, respx_mock)
    assert tokens["token_type"] == "Bearer" and tokens["expires_in"] == 3600
    assert tokens["access_token"] != "api-at-1" and tokens["refresh_token"] != "api-rt-1"
    dump = json.dumps({k.decode(): (await redis.type(k)).decode() for k in await redis.keys("*")})
    assert tokens["access_token"] not in dump and tokens["refresh_token"] not in dump
    for key in await redis.keys(PREFIX + "session:*"):
        if (await redis.type(key)) == b"string":
            raw = await redis.get(key)
            assert b"api-at-1" not in raw and b"api-rt-1" not in raw


async def test_code_cannot_be_reused(app, respx_mock):
    from tests.auth.oauth_helpers import mock_google_and_api
    from entrepataseturnos_mcp.auth.google import pkce_pair  # noqa: F401

    mock_google_and_api(respx_mock)
    async with http(app) as client:
        client_id = await register_client(client)
        url, verifier = await start_authorize(client, client_id)
        cb = await client.get("/oauth/google/callback", params={"state": query(url)["state"], "code": "g"})
        code = query(cb.headers["location"])["code"]
        assert query(cb.headers["location"])["state"] == "client-state"
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": CLIENT_REDIRECT,
                "client_id": client_id, "code_verifier": verifier}
        assert (await client.post("/token", data=form)).status_code == 200
        again = await client.post("/token", data=form)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


async def test_bearer_resolves_to_session_and_tool_acts_as_user(app, respx_mock):
    tokens = await sign_in(app, respx_mock)
    pets = respx_mock.get(f"{API}/v1/pets").mock(
        return_value=httpx.Response(200, json={"items": [], "page": {"number": 0, "size": 20, "totalItems": 0, "totalPages": 0}})
    )
    async with mcp_client(app, bearer=tokens["access_token"]) as c:
        assert not (await c.call_tool("list_my_pets", {})).is_error
    assert pets.calls.last.request.headers["Authorization"] == "Bearer api-at-1"


async def test_refresh_token_rotates(app, respx_mock):
    tokens = await sign_in(app, respx_mock)
    form = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": tokens["client_id"]}
    async with http(app) as client:
        first = await client.post("/token", data=form)
        assert first.status_code == 200, first.text
        assert first.json()["refresh_token"] != tokens["refresh_token"]
        reused = await client.post("/token", data=form)
    assert reused.status_code == 400


async def test_revocation_ends_api_session_and_all_tokens(app, respx_mock):
    tokens = await sign_in(app, respx_mock)
    delete = respx_mock.delete(f"{API}/v1/auth/sessions/900").mock(return_value=httpx.Response(204))
    async with http(app) as client:
        r = await client.post("/revoke", data={"token": tokens["access_token"], "client_id": tokens["client_id"], "client_secret": ""})
        assert r.status_code == 200
    assert delete.called
    async with http(app) as client:
        r = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                              headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 401
    page = await app.state.components.provider.load_refresh_token(
        await app.state.components.provider.get_client(tokens["client_id"]), tokens["refresh_token"]
    )
    assert page is None
    _ = result_payload  # imported for symmetry with other modules
