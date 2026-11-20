"""Shared runtime services handed to tool builders (dependency injection by construction)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .api.client import ApiClient
from .auth.session import SessionService, current_session_id


@dataclass(frozen=True)
class Services:
    api: ApiClient
    sessions: SessionService

    async def as_user[T](self, operation: Callable[[str], Awaitable[T]]) -> T:
        """Run ``operation(api_access_token)`` as the signed-in caller of the current request."""
        return await self.sessions.call(current_session_id(), operation)
