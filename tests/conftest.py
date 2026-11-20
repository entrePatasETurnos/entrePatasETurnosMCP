"""Shared fixtures: settings, mocked API (respx), fake Redis, the Starlette app, and in-process
MCP clients that talk Streamable HTTP to the app through an ASGI transport."""

from __future__ import annotations

import base64
import contextlib
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import fakeredis
import httpx2
import mcp_types as types
import pytest
import respx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette

from entrepataseturnos_mcp.app import Components, build_components, create_app
from entrepataseturnos_mcp.auth.store import ApiSession
from entrepataseturnos_mcp.config import Settings

API = "http://api.test"
PUBLIC = "http://localhost:8000"
TEST_KEY = base64.b64encode(bytes(range(32))).decode()
GOOGLE_SECRET = "google-client-secret-value"
REDIS_PASSWORD = "redis-password-value"
API_ACCESS = "api-at-1"
API_REFRESH = "api-rt-1"

Elicitation = Literal["accept", "reject", "decline", "cancel"] | None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_base_url=API,
        public_base_url=PUBLIC,
        google_client_id="google-client-id",
        google_client_secret=GOOGLE_SECRET,  # type: ignore[arg-type]
        redis_url=f"redis://:{REDIS_PASSWORD}@localhost:6379/0",  # type: ignore[arg-type]
        token_encryption_key=TEST_KEY,  # type: ignore[arg-type]
    )


@pytest.fixture
def redis() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis()


@pytest.fixture
def respx_mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
def components(settings: Settings, redis: fakeredis.FakeAsyncRedis) -> Components:
    return build_components(settings, redis=redis)


@pytest.fixture
async def app(
    settings: Settings, components: Components, respx_mock: respx.MockRouter
) -> AsyncIterator[Starlette]:
    application = create_app(settings, components)
    async with application.router.lifespan_context(application):
        yield application


async def seed_session(
    components: Components,
    *,
    sid: str = "sid-1",
    user_id: str = "42",
    access_token: str = API_ACCESS,
    access_expires_in: timedelta = timedelta(minutes=10),
) -> str:
    now = datetime.now(UTC)
    await components.store.save_session(
        sid,
        ApiSession(
            api_session_id="900",
            user_id=user_id,
            access_token=access_token,
            access_expires_at=now + access_expires_in,
            refresh_token=API_REFRESH,
            refresh_expires_at=now + timedelta(days=30),
            created_at=now,
        ),
    )
    return sid


@pytest.fixture
async def bearer(components: Components) -> str:
    """An MCP access token for a signed-in user (user 42, API token ``api-at-1``)."""
    sid = await seed_session(components)
    token = await components.provider._issue("test-client", sid, "42", [], None)
    return token.access_token


@dataclass
class Recorder:
    prompts: list[str] = field(default_factory=list)


@contextlib.asynccontextmanager
async def mcp_client(
    app: Starlette,
    *,
    path: str = "/mcp",
    bearer: str | None = None,
    elicitation: Elicitation = "accept",
    mode: str = "auto",
    recorder: Recorder | None = None,
) -> AsyncIterator[Client]:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url=PUBLIC, headers=headers, timeout=30
    )

    async def on_elicit(_ctx: Any, params: Any) -> types.ElicitResult:
        if recorder is not None:
            recorder.prompts.append(params.message)
        if elicitation == "accept":
            return types.ElicitResult(action="accept", content={"confirm": True})
        if elicitation == "reject":
            return types.ElicitResult(action="accept", content={"confirm": False})
        return types.ElicitResult(action=elicitation or "cancel")

    kwargs: dict[str, Any] = {"mode": mode}
    if elicitation is not None:
        kwargs["elicitation_callback"] = on_elicit
    async with http:
        async with Client(streamable_http_client(f"{PUBLIC}{path}", http_client=http), **kwargs) as client:
            yield client


def result_payload(result: types.CallToolResult) -> dict[str, Any]:
    """Structured result on success; the decoded error payload on failure."""
    if result.is_error:
        text = result.content[0].text  # type: ignore[union-attr]
        _, _, body = text.partition(": ")
        try:
            return {"is_error": True, **json.loads(body)}
        except ValueError:
            return {"is_error": True, "error_code": "unstructured", "message": text}
    assert result.structured_content is not None
    return dict(result.structured_content)


def api_calls(router: respx.MockRouter) -> list[tuple[str, str]]:
    return [(c.request.method, c.request.url.path) for c in router.calls if c.request.url.host == "api.test"]


def last_json(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


async def call(
    app: Starlette,
    tool: str,
    args: dict[str, Any],
    *,
    bearer: str | None,
    elicitation: Elicitation = "accept",
    path: str = "/mcp",
    recorder: Recorder | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    async with mcp_client(
        app, bearer=bearer, elicitation=elicitation, path=path, recorder=recorder, mode=mode
    ) as client:
        await client.list_tools()
        return result_payload(await client.call_tool(tool, args))


def future(days: int = 10, hour: int = 14) -> str:
    """An ISO date-time ``days`` from now at ``hour``:00 in -03:00."""
    from datetime import timezone

    tz = timezone(timedelta(hours=-3))
    d = (datetime.now(tz) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return d.isoformat()
