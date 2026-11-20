"""Starlette composition: probes, ``/public/mcp``, and the OAuth-protected ``/mcp`` with its
authorization-server routes."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from mcp.server.transport_security import TransportSecuritySettings
from redis.asyncio import Redis
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from .api import auth as api_auth
from .api.client import ApiClient
from .auth.crypto import TokenCipher
from .auth.google import GoogleClient
from .auth.provider import RedisOAuthProvider
from .auth.session import SessionService
from .auth.store import Store
from .config import Settings
from .health import Readiness, healthz
from .servers import build_authenticated_server, build_public_server
from .services import Services


@dataclass
class Components:
    """Everything ``create_app`` wires together; exposed for tests."""

    settings: Settings
    api: ApiClient
    redis: Redis
    store: Store
    sessions: SessionService
    google: GoogleClient
    provider: RedisOAuthProvider
    services: Services


def build_components(
    settings: Settings,
    *,
    redis: Redis | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    google_transport: httpx.AsyncBaseTransport | None = None,
) -> Components:
    api = ApiClient(settings.api_base_url, settings.api_timeout_seconds, transport=api_transport)
    if redis is None:
        redis = Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
        )
    store = Store(redis, TokenCipher(settings.encryption_key_bytes))
    sessions = SessionService(store, api)
    google = GoogleClient(settings, transport=google_transport)
    provider = RedisOAuthProvider(settings, store, sessions, google)
    return Components(
        settings=settings,
        api=api,
        redis=redis,
        store=store,
        sessions=sessions,
        google=google,
        provider=provider,
        services=Services(api=api, sessions=sessions),
    )


def create_app(settings: Settings, components: Components | None = None) -> Starlette:
    c = components or build_components(settings)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings.allowed_host_list,
        allowed_origins=[settings.public_base_url, "http://localhost:*", "http://127.0.0.1:*"],
    )
    authenticated = build_authenticated_server(settings, c.provider, c.services)
    public = build_public_server(settings, c.api)
    authenticated_app = authenticated.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=False,  # SSE responses carry legacy-protocol elicitation prompts
        transport_security=security,
    )
    public_app = public.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=False,
        transport_security=security,
    )

    readiness = Readiness(
        {
            "redis": (c.store.ping, 1.0),
            "api": (lambda: api_auth.info(c.api, timeout=2.0), 2.5),
        }
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            stack.push_async_callback(c.redis.aclose)
            stack.push_async_callback(c.google.aclose)
            stack.push_async_callback(c.api.aclose)
            await stack.enter_async_context(authenticated_app.router.lifespan_context(authenticated_app))
            await stack.enter_async_context(public_app.router.lifespan_context(public_app))
            yield

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readiness.endpoint, methods=["GET"]),
            Mount("/public", app=public_app),
            Mount("", app=authenticated_app),
        ],
        lifespan=lifespan,
    )
    app.state.components = c
    return app
