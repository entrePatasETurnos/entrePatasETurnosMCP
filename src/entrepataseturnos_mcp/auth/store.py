"""Redis-backed storage for OAuth and API-session state (data-model.md §2).

Every key lives under ``epet:mcp:``; every record has a TTL. Issued MCP tokens and codes are
stored only by their SHA-256 hash, and API tokens are stored encrypted.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .crypto import TokenCipher, hash_token
from .errors import SessionStoreUnavailable

PREFIX = "epet:mcp:"
PENDING_TTL = 600
CODE_TTL = 300
LOCK_TTL_MS = 10_000

T = TypeVar("T")


class ApiSession(BaseModel):
    """The signed-in user's API session, with tokens decrypted (in memory only)."""

    api_session_id: str
    user_id: str
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    created_at: datetime


class PendingAuthorization(BaseModel):
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: list[str]
    client_state: str | None
    resource: str | None
    google_code_verifier: str


class StoredCode(BaseModel):
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: list[str]
    resource: str | None
    sid: str
    user_id: str
    expires_at: float


class StoredToken(BaseModel):
    client_id: str
    sid: str
    user_id: str
    scopes: list[str]
    resource: str | None
    expires_at: int


def _k(*parts: str) -> str:
    return PREFIX + ":".join(parts)


async def _guard[T](op: Callable[[], Awaitable[T]]) -> T:
    try:
        return await op()
    except (RedisError, OSError) as exc:
        raise SessionStoreUnavailable("session store unavailable") from exc


class Store:
    def __init__(self, redis: Redis, cipher: TokenCipher) -> None:
        self.redis = redis
        self._cipher = cipher

    # ------------------------------------------------------------------ API sessions
    async def save_session(self, sid: str, session: ApiSession) -> None:
        record = session.model_dump(mode="json")
        record["access_token"] = self._cipher.encrypt(session.access_token)
        record["refresh_token"] = self._cipher.encrypt(session.refresh_token)
        ttl = max(1, int(session.refresh_expires_at.timestamp() - time.time()))
        await _guard(lambda: self.redis.set(_k("session", sid), json.dumps(record), ex=ttl))

    async def load_session(self, sid: str) -> ApiSession | None:
        raw = await _guard(lambda: self.redis.get(_k("session", sid)))
        if raw is None:
            return None
        record = json.loads(raw)
        record["access_token"] = self._cipher.decrypt(record["access_token"])
        record["refresh_token"] = self._cipher.decrypt(record["refresh_token"])
        return ApiSession.model_validate(record)

    async def acquire_refresh_lock(self, sid: str, owner: str) -> bool:
        ok = await _guard(
            lambda: self.redis.set(_k("session", sid, "lock"), owner, nx=True, px=LOCK_TTL_MS)
        )
        return bool(ok)

    async def release_refresh_lock(self, sid: str, owner: str) -> None:
        key = _k("session", sid, "lock")
        current = await _guard(lambda: self.redis.get(key))
        if current is not None and (current.decode() if isinstance(current, bytes) else current) == owner:
            await _guard(lambda: self.redis.delete(key))

    async def delete_session_cascade(self, sid: str) -> None:
        """Delete the session and every MCP token issued for it."""
        index = _k("session", sid, "tokens")
        members = await _guard(lambda: self.redis.smembers(index))
        keys = [_k("session", sid), _k("session", sid, "lock"), index]
        keys += [_k(m.decode() if isinstance(m, bytes) else m) for m in members]
        await _guard(lambda: self.redis.delete(*keys))

    # ---------------------------------------------------------------- OAuth clients
    async def save_client(self, client_id: str, data: dict[str, Any]) -> None:
        await _guard(lambda: self.redis.set(_k("client", client_id), json.dumps(data)))

    async def load_client(self, client_id: str) -> dict[str, Any] | None:
        raw = await _guard(lambda: self.redis.get(_k("client", client_id)))
        return None if raw is None else dict(json.loads(raw))

    # ----------------------------------------------------- pending authorizations
    async def save_pending(self, state: str, pending: PendingAuthorization) -> None:
        await _guard(
            lambda: self.redis.set(
                _k("pending", hash_token(state)), pending.model_dump_json(), ex=PENDING_TTL
            )
        )

    async def consume_pending(self, state: str) -> PendingAuthorization | None:
        raw = await _guard(lambda: self.redis.getdel(_k("pending", hash_token(state))))
        return None if raw is None else PendingAuthorization.model_validate_json(raw)

    # --------------------------------------------------------- authorization codes
    async def save_code(self, code: str, stored: StoredCode) -> None:
        await _guard(
            lambda: self.redis.set(_k("code", hash_token(code)), stored.model_dump_json(), ex=CODE_TTL)
        )

    async def load_code(self, code: str) -> StoredCode | None:
        raw = await _guard(lambda: self.redis.get(_k("code", hash_token(code))))
        return None if raw is None else StoredCode.model_validate_json(raw)

    async def consume_code(self, code: str) -> StoredCode | None:
        raw = await _guard(lambda: self.redis.getdel(_k("code", hash_token(code))))
        return None if raw is None else StoredCode.model_validate_json(raw)

    # ------------------------------------------------------- access/refresh tokens
    async def save_token(self, kind: str, token: str, stored: StoredToken) -> None:
        """``kind`` is ``at`` (access) or ``rt`` (refresh)."""
        name = f"{kind}:{hash_token(token)}"
        ttl = max(1, stored.expires_at - int(time.time()))

        async def op() -> None:
            pipe = self.redis.pipeline(transaction=True)
            pipe.set(_k(name), stored.model_dump_json(), ex=ttl)
            pipe.sadd(_k("session", stored.sid, "tokens"), name)
            await pipe.execute()

        await _guard(op)

    async def load_token(self, kind: str, token: str) -> StoredToken | None:
        raw = await _guard(lambda: self.redis.get(_k(f"{kind}:{hash_token(token)}")))
        return None if raw is None else StoredToken.model_validate_json(raw)

    async def delete_token(self, kind: str, token: str, sid: str) -> None:
        name = f"{kind}:{hash_token(token)}"

        async def op() -> None:
            pipe = self.redis.pipeline(transaction=True)
            pipe.delete(_k(name))
            pipe.srem(_k("session", sid, "tokens"), name)
            await pipe.execute()

        await _guard(op)

    async def ping(self) -> bool:
        return bool(await _guard(lambda: self.redis.ping()))  # type: ignore[misc]
