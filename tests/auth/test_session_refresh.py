"""T029: SessionService.api_token refresh rules."""

import json
from datetime import timedelta

import anyio
import fakeredis
import httpx
import pytest

from entrepataseturnos_mcp.auth.errors import SessionStoreUnavailable, SignInRequired
from entrepataseturnos_mcp.auth.store import PREFIX
from tests.auth.oauth_helpers import session_body
from tests.conftest import API, API_REFRESH, seed_session

pytestmark = pytest.mark.anyio
REFRESH = f"{API}/v1/auth/sessions/900/refresh"


async def test_fresh_token_used_without_api_call(components, respx_mock):
    sid = await seed_session(components)
    route = respx_mock.post(REFRESH)
    assert await components.sessions.api_token(sid) == "api-at-1"
    assert not route.called


async def test_expiring_token_is_refreshed_and_rotated_tokens_stored(components, respx_mock, redis):
    sid = await seed_session(components, access_expires_in=timedelta(seconds=30))
    route = respx_mock.post(REFRESH).mock(return_value=httpx.Response(200, json=session_body("api-at-2", "api-rt-2")))
    assert await components.sessions.api_token(sid) == "api-at-2"
    assert json.loads(route.calls.last.request.content) == {"refreshToken": API_REFRESH}
    stored = await components.store.load_session(sid)
    assert stored.refresh_token == "api-rt-2"
    assert b"api-rt-2" not in await redis.get(PREFIX + f"session:{sid}")


async def test_concurrent_callers_refresh_once(components, respx_mock):
    sid = await seed_session(components, access_expires_in=timedelta(seconds=0))

    async def slow(_request):
        await anyio.sleep(0.2)
        return httpx.Response(200, json=session_body("api-at-2", "api-rt-2"))

    route = respx_mock.post(REFRESH).mock(side_effect=slow)
    results: list[str] = []

    async def call():
        results.append(await components.sessions.api_token(sid))

    async with anyio.create_task_group() as tg:
        for _ in range(3):
            tg.start_soon(call)
    assert results == ["api-at-2"] * 3
    assert route.call_count == 1


async def test_refresh_in_progress_is_retried_once(components, respx_mock):
    sid = await seed_session(components, access_expires_in=timedelta(seconds=0))
    route = respx_mock.post(REFRESH).mock(
        side_effect=[
            httpx.Response(409, json={"error": "refresh_in_progress", "message": "m"}),
            httpx.Response(200, json=session_body("api-at-3", "api-rt-3")),
        ]
    )
    assert await components.sessions.api_token(sid) == "api-at-3"
    assert route.call_count == 2


async def test_rejected_refresh_signs_out(components, respx_mock):
    sid = await seed_session(components, access_expires_in=timedelta(seconds=0))
    await components.provider._issue("c", sid, "42", [], None)
    respx_mock.post(REFRESH).mock(return_value=httpx.Response(401, json={"error": "invalid_refresh_token", "message": "m"}))
    with pytest.raises(SignInRequired):
        await components.sessions.api_token(sid)
    assert await components.store.load_session(sid) is None
    assert await components.store.redis.keys(PREFIX + "at:*") == []


async def test_missing_session_requires_sign_in(components):
    with pytest.raises(SignInRequired):
        await components.sessions.api_token("nope")


async def test_store_unavailable(components):
    class Broken(fakeredis.FakeAsyncRedis):
        async def get(self, *a, **k):
            raise ConnectionError("down")

    components.store.redis = Broken()
    with pytest.raises(SessionStoreUnavailable):
        await components.sessions.api_token("sid")
