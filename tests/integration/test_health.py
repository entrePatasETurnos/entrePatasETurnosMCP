"""T046: /healthz and /readyz."""

import fakeredis
import httpx
import pytest

from entrepataseturnos_mcp import health
from tests.auth.oauth_helpers import http
from tests.conftest import API, GOOGLE_SECRET, REDIS_PASSWORD

pytestmark = pytest.mark.anyio


class DownRedis(fakeredis.FakeAsyncRedis):
    async def ping(self, *a, **k):
        raise ConnectionError("down")


async def _get(app, path):
    async with http(app) as client:
        return await client.get(path)


async def test_healthz_ok_even_when_dependencies_down(app, components, respx_mock):
    components.store.redis = DownRedis()
    respx_mock.get(f"{API}/v1/info").mock(return_value=httpx.Response(500))
    r = await _get(app, "/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_ready_when_redis_and_api_ok(app, respx_mock):
    respx_mock.get(f"{API}/v1/info").mock(return_value=httpx.Response(200, json={"name": "api"}))
    r = await _get(app, "/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"settings": "ok", "redis": "ok", "api": "ok"}}


@pytest.mark.parametrize("failure", ["redis", "api_5xx", "api_timeout"])
async def test_not_ready_names_failing_check(app, components, respx_mock, failure):
    info = respx_mock.get(f"{API}/v1/info")
    info.mock(return_value=httpx.Response(200, json={}))
    if failure == "redis":
        components.store.redis = DownRedis()
    elif failure == "api_5xx":
        info.mock(return_value=httpx.Response(503, json={"error": "x", "message": "m"}))
    else:
        info.mock(side_effect=httpx.ReadTimeout("slow"))
    r = await _get(app, "/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis" if failure == "redis" else "api"] == "fail"
    for secret in (REDIS_PASSWORD, GOOGLE_SECRET, "redis://"):
        assert secret not in r.text


async def test_results_are_cached(app, respx_mock, monkeypatch):
    route = respx_mock.get(f"{API}/v1/info").mock(return_value=httpx.Response(200, json={}))
    await _get(app, "/readyz")
    await _get(app, "/readyz")
    assert route.call_count == 1
    monkeypatch.setattr(health, "CACHE_SECONDS", 0.0)
    await _get(app, "/readyz")
    assert route.call_count == 2
