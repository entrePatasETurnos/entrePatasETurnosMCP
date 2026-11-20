"""The signed-in user's API session: creation, refresh with a shared lock, and sign-out (R3)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token

from ..api import auth as api_auth
from ..api.client import ApiClient
from ..api.errors import ApiError, UpstreamTimeout
from .crypto import new_token
from .errors import SignInRequired
from .store import ApiSession, Store

logger = logging.getLogger(__name__)


def current_session_id() -> str:
    """The session bound to the verified MCP bearer token. Identity never comes from tool input."""
    token = get_access_token()
    sid = (token.claims or {}).get("sid") if token is not None else None
    if not isinstance(sid, str) or not sid:
        raise SignInRequired("no authenticated session")
    return sid


class SessionService:
    def __init__(
        self,
        store: Store,
        api: ApiClient,
        *,
        refresh_margin_seconds: int = 60,
        lock_wait_seconds: float = 5.0,
    ) -> None:
        self._store = store
        self._api = api
        self._margin = timedelta(seconds=refresh_margin_seconds)
        self._lock_wait = lock_wait_seconds

    async def create_from_google(self, id_token: str) -> tuple[str, ApiSession]:
        tokens = await api_auth.create_google_session(self._api, id_token)
        session = ApiSession(
            api_session_id=tokens.session_id,
            user_id=tokens.user_id,
            access_token=tokens.access_token,
            access_expires_at=tokens.access_expires_at,
            refresh_token=tokens.refresh_token,
            refresh_expires_at=tokens.refresh_expires_at,
            created_at=datetime.now(UTC),
        )
        sid = new_token()
        await self._store.save_session(sid, session)
        return sid, session

    async def session(self, sid: str) -> ApiSession:
        session = await self._store.load_session(sid)
        if session is None:
            raise SignInRequired("session not found")
        return session

    def _fresh(self, session: ApiSession) -> bool:
        return session.access_expires_at > datetime.now(UTC) + self._margin

    async def api_token(self, sid: str, *, force_refresh: bool = False) -> str:
        session = await self.session(sid)
        if not force_refresh and self._fresh(session):
            return session.access_token
        stale = session.access_token
        owner = new_token()
        if await self._store.acquire_refresh_lock(sid, owner):
            try:
                current = await self.session(sid)
                if current.access_token != stale and self._fresh(current):
                    return current.access_token  # another replica refreshed meanwhile
                return await self._refresh(sid, current)
            finally:
                await self._store.release_refresh_lock(sid, owner)
        # Someone else is refreshing: wait for their result.
        with anyio.move_on_after(self._lock_wait):
            while True:
                await anyio.sleep(0.1)
                current = await self.session(sid)
                if current.access_token != stale and self._fresh(current):
                    return current.access_token
        raise UpstreamTimeout("session refresh did not complete in time")

    async def _refresh(self, sid: str, session: ApiSession) -> str:
        for attempt in range(2):
            try:
                tokens = await api_auth.refresh_session(
                    self._api, session.api_session_id, session.refresh_token
                )
                break
            except ApiError as exc:
                if exc.code == "refresh_in_progress" and attempt == 0:
                    await anyio.sleep(0.5)
                    continue
                if exc.status == 401 or exc.code == "invalid_refresh_token":
                    logger.info("api session refresh rejected; signing out", extra={"sid_hint": sid[:6]})
                    await self._store.delete_session_cascade(sid)
                    raise SignInRequired("refresh rejected") from None
                raise
        else:  # pragma: no cover - loop always breaks or raises
            raise SignInRequired("refresh failed")
        updated = session.model_copy(
            update={
                "access_token": tokens.access_token,
                "access_expires_at": tokens.access_expires_at,
                "refresh_token": tokens.refresh_token,
                "refresh_expires_at": tokens.refresh_expires_at,
            }
        )
        await self._store.save_session(sid, updated)
        return updated.access_token

    async def call[T](self, sid: str, operation: Callable[[str], Awaitable[T]]) -> T:
        """Run an API operation as the user, refreshing once if the API says the token expired."""
        token = await self.api_token(sid)
        try:
            return await operation(token)
        except ApiError as exc:
            if exc.status != 401:
                raise
        token = await self.api_token(sid, force_refresh=True)
        try:
            return await operation(token)
        except ApiError as exc:
            if exc.status == 401:
                await self._store.delete_session_cascade(sid)
                raise SignInRequired("the API rejected the session") from None
            raise

    async def sign_out(self, sid: str) -> None:
        """End the API session (best effort) and always delete local state."""
        session = await self._store.load_session(sid)
        if session is not None:
            try:
                await api_auth.delete_session(
                    self._api, session.api_session_id, session.access_token
                )
            except Exception as exc:  # noqa: BLE001 - local sign-out must still happen
                logger.warning("api session delete failed", extra={"error": type(exc).__name__})
        await self._store.delete_session_cascade(sid)
