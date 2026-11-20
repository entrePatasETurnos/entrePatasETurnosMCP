"""T030: /mcp authentication, metadata, sign_out, multi-replica, token secrecy."""

import json
import logging

import httpx
import pytest

from entrepataseturnos_mcp.app import build_components, create_app
from tests.auth.oauth_helpers import http
from tests.conftest import API, API_REFRESH, PUBLIC, mcp_client, result_payload

pytestmark = pytest.mark.anyio
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
EMPTY_PETS = {"items": [], "page": {"number": 0, "size": 20, "totalItems": 0, "totalPages": 0}}


@pytest.mark.parametrize("auth", [None, "Bearer not-a-token"])
async def test_mcp_requires_valid_bearer(app, auth):
    headers = {"Accept": "application/json, text/event-stream"}
    if auth:
        headers["Authorization"] = auth
    async with http(app) as client:
        r = await client.post("/mcp", json=LIST, headers=headers)
    assert r.status_code == 401
    assert "oauth-protected-resource/mcp" in r.headers["www-authenticate"]


async def test_metadata_advertises_endpoints(app):
    async with http(app) as client:
        meta = (await client.get("/.well-known/oauth-authorization-server")).json()
        prm = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
    assert meta["issuer"].rstrip("/") == PUBLIC
    for key, path in [("authorization_endpoint", "/authorize"), ("token_endpoint", "/token"),
                      ("registration_endpoint", "/register"), ("revocation_endpoint", "/revoke")]:
        assert meta[key] == f"{PUBLIC}{path}"
    assert prm["resource"].rstrip("/") == f"{PUBLIC}/mcp"


async def test_sign_out_ends_session(app, bearer, respx_mock):
    delete = respx_mock.delete(f"{API}/v1/auth/sessions/900").mock(return_value=httpx.Response(204))
    async with mcp_client(app, bearer=bearer) as c:
        await c.list_tools()  # the client validates results against cached schemas
        out = result_payload(await c.call_tool("sign_out", {}))
    assert out == {"signed_out": True}
    assert delete.calls.last.request.headers["Authorization"] == "Bearer api-at-1"
    async with http(app) as client:
        r = await client.post("/mcp", json=LIST, headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 401


async def test_sign_out_without_elicitation_needs_confirmation(app, bearer, respx_mock):
    delete = respx_mock.delete(f"{API}/v1/auth/sessions/900").mock(return_value=httpx.Response(204))
    async with mcp_client(app, bearer=bearer, elicitation=None) as c:
        await c.list_tools()
        out = result_payload(await c.call_tool("sign_out", {}))
        assert out["error_code"] == "confirmation_required" and not delete.called
        assert result_payload(await c.call_tool("sign_out", {"user_confirmed": True})) == {"signed_out": True}


async def test_two_replicas_share_sessions(settings, redis, bearer, respx_mock):
    respx_mock.get(f"{API}/v1/pets").mock(return_value=httpx.Response(200, json=EMPTY_PETS))
    for _ in range(2):
        replica = create_app(settings, build_components(settings, redis=redis))
        async with replica.router.lifespan_context(replica):
            async with mcp_client(replica, bearer=bearer) as c:
                assert not (await c.call_tool("list_my_pets", {})).is_error


async def test_tokens_never_reach_results_or_logs(app, bearer, respx_mock, caplog):
    caplog.set_level(logging.DEBUG)
    respx_mock.get(f"{API}/v1/pets").mock(return_value=httpx.Response(200, json=EMPTY_PETS))
    async with mcp_client(app, bearer=bearer) as c:
        r = await c.call_tool("list_my_pets", {})
    text = json.dumps(r.model_dump(mode="json")) + caplog.text
    for secret in ("api-at-1", API_REFRESH):
        assert secret not in text
