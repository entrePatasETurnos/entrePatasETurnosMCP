"""T038: list_my_pets."""

import httpx
import pytest

from tests.conftest import API, api_calls, call

pytestmark = pytest.mark.anyio
REFRESH = f"{API}/v1/auth/sessions/900/refresh"
BODY = {
    "items": [{"id": 1, "name": "Rex", "species": "DOG", "gender": "MALE", "age": 3,
               "photos": [{"id": 9}], "createdAt": "x", "updatedAt": "y", "_links": {"self": {}}}],
    "page": {"number": 0, "size": 20, "totalItems": 1, "totalPages": 1},
    "_links": {},
}


async def test_valid_call_trims_output(app, bearer, respx_mock):
    route = respx_mock.get(f"{API}/v1/pets").mock(return_value=httpx.Response(200, json=BODY))
    out = await call(app, "list_my_pets", {"page": 0, "size": 5}, bearer=bearer)
    assert out == {
        "items": [{"id": 1, "name": "Rex", "species": "DOG", "gender": "MALE", "age": 3}],
        "page": {"number": 0, "size": 20, "total_items": 1, "total_pages": 1},
    }
    req = route.calls.last.request
    assert dict(req.url.params) == {"page": "0", "size": "5"}
    assert req.headers["Authorization"] == "Bearer api-at-1"


@pytest.mark.parametrize("args", [{"size": 101}, {"page": -1}, {"user_id": 7}, {"size": "10"}])
async def test_invalid_input_never_calls_api(app, bearer, respx_mock, args):
    out = await call(app, "list_my_pets", args, bearer=bearer)
    assert out["error_code"] == "validation_error"
    assert api_calls(respx_mock) == []


async def test_api_401_then_refresh_failure_is_sign_in_required(app, bearer, respx_mock):
    respx_mock.get(f"{API}/v1/pets").mock(return_value=httpx.Response(401))
    respx_mock.post(REFRESH).mock(return_value=httpx.Response(401, json={"error": "invalid_refresh_token", "message": "m"}))
    out = await call(app, "list_my_pets", {}, bearer=bearer)
    assert out["error_code"] == "sign_in_required"


async def test_api_401_then_successful_refresh_retries_once(app, bearer, respx_mock):
    from tests.auth.oauth_helpers import session_body

    pets = respx_mock.get(f"{API}/v1/pets").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=BODY)]
    )
    respx_mock.post(REFRESH).mock(return_value=httpx.Response(200, json=session_body("api-at-2", "api-rt-2")))
    out = await call(app, "list_my_pets", {}, bearer=bearer)
    assert out["items"][0]["name"] == "Rex"
    assert pets.calls.last.request.headers["Authorization"] == "Bearer api-at-2"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(502, text="bad gateway"), "upstream_unavailable"),
        (httpx.ReadTimeout("slow"), "upstream_timeout"),
        (httpx.ConnectError("down"), "upstream_unavailable"),
    ],
)
async def test_upstream_failures(app, bearer, respx_mock, response, code):
    route = respx_mock.get(f"{API}/v1/pets")
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    out = await call(app, "list_my_pets", {}, bearer=bearer)
    assert out["is_error"] and out["error_code"] == code


async def test_no_bearer_is_rejected(app):
    from tests.auth.oauth_helpers import http

    async with http(app) as client:
        r = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                            "params": {"name": "list_my_pets", "arguments": {}}})
    assert r.status_code == 401
