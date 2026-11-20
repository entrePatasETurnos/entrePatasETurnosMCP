import httpx
import pytest
import respx

from entrepataseturnos_mcp.api.client import ApiClient
from entrepataseturnos_mcp.api.errors import ApiError, OutcomeUnknown, UpstreamTimeout, UpstreamUnavailable

pytestmark = pytest.mark.anyio
API = "http://api.test"


@pytest.fixture
async def client():
    c = ApiClient(API, 0.5)
    yield c
    await c.aclose()


async def test_base_url_correlation_id_and_optional_bearer(client, respx_mock: respx.MockRouter):
    route = respx_mock.get(f"{API}/v1/pets").mock(return_value=httpx.Response(200, json={"ok": 1}))
    assert await client._get("/v1/pets") == {"ok": 1}
    req = route.calls.last.request
    assert req.headers["X-Correlation-Id"]
    assert "Authorization" not in req.headers
    await client._get("/v1/pets", token="tok")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"


async def test_none_params_dropped(client, respx_mock):
    route = respx_mock.get(f"{API}/v1/x").mock(return_value=httpx.Response(200, json={}))
    await client._get("/v1/x", params={"a": 1, "b": None})
    assert dict(route.calls.last.request.url.params) == {"a": "1"}


async def test_unversioned_path_rejected(client):
    with pytest.raises(AssertionError):
        await client._get("/pets")


async def test_get_retried_once_on_connect_error(client, respx_mock):
    route = respx_mock.get(f"{API}/v1/x").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={"ok": True})]
    )
    assert await client._get("/v1/x") == {"ok": True}
    assert route.call_count == 2


@pytest.mark.parametrize("method", ["_post", "_put", "_delete"])
async def test_writes_never_retried(client, respx_mock, method):
    route = respx_mock.route(path="/v1/x").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(UpstreamUnavailable):
        await getattr(client, method)("/v1/x")
    assert route.call_count == 1


async def test_read_timeout_on_get_is_upstream_timeout(client, respx_mock):
    respx_mock.get(f"{API}/v1/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(UpstreamTimeout):
        await client._get("/v1/x")


async def test_read_timeout_on_write_is_outcome_unknown(client, respx_mock):
    respx_mock.post(f"{API}/v1/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(OutcomeUnknown):
        await client._post("/v1/x", json={})


async def test_error_body_mapped_with_fields_and_extras(client, respx_mock):
    respx_mock.post(f"{API}/v1/x").mock(
        return_value=httpx.Response(
            409,
            json={"error": "pet_already_booked", "message": "já reservado", "petIds": [3, 5], "_links": {}},
        )
    )
    with pytest.raises(ApiError) as exc:
        await client._post("/v1/x", json={})
    assert (exc.value.code, exc.value.status) == ("pet_already_booked", 409)
    assert exc.value.extras == {"petIds": [3, 5]}

    respx_mock.post(f"{API}/v1/y").mock(
        return_value=httpx.Response(
            400, json={"error": "invalid_request", "message": "m", "fields": {"petIds": "inválido"}}
        )
    )
    with pytest.raises(ApiError) as exc:
        await client._post("/v1/y", json={})
    assert exc.value.fields == {"petIds": "inválido"}


async def test_non_json_errors(client, respx_mock):
    respx_mock.get(f"{API}/v1/a").mock(return_value=httpx.Response(502, text="bad gateway"))
    with pytest.raises(ApiError) as exc:
        await client._get("/v1/a")
    assert exc.value.code == "upstream_unavailable"
    respx_mock.get(f"{API}/v1/b").mock(return_value=httpx.Response(418, text="teapot"))
    with pytest.raises(ApiError) as exc:
        await client._get("/v1/b")
    assert exc.value.code == "upstream_invalid_response"


async def test_success_with_malformed_json(client, respx_mock):
    respx_mock.get(f"{API}/v1/a").mock(return_value=httpx.Response(200, text="{not json"))
    with pytest.raises(ApiError) as exc:
        await client._get("/v1/a")
    assert exc.value.code == "upstream_invalid_response"


async def test_204_returns_none(client, respx_mock):
    respx_mock.delete(f"{API}/v1/a").mock(return_value=httpx.Response(204))
    assert await client._delete("/v1/a") is None
