from datetime import UTC, datetime, timedelta

import fakeredis
import pytest

from entrepataseturnos_mcp.auth.crypto import TokenCipher, hash_token
from entrepataseturnos_mcp.auth.store import (
    PREFIX,
    ApiSession,
    PendingAuthorization,
    Store,
    StoredCode,
    StoredToken,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def store() -> Store:
    return Store(fakeredis.FakeAsyncRedis(), TokenCipher(bytes(32)))


def _session() -> ApiSession:
    now = datetime.now(UTC)
    return ApiSession(
        api_session_id="1",
        user_id="42",
        access_token="api-at-secret",
        access_expires_at=now + timedelta(minutes=15),
        refresh_token="api-rt-secret",
        refresh_expires_at=now + timedelta(days=30),
        created_at=now,
    )


async def test_session_tokens_encrypted_at_rest_with_ttl(store: Store) -> None:
    await store.save_session("s1", _session())
    raw = await store.redis.get(PREFIX + "session:s1")
    assert b"api-at-secret" not in raw and b"api-rt-secret" not in raw
    ttl = await store.redis.ttl(PREFIX + "session:s1")
    assert 29 * 86400 < ttl <= 30 * 86400
    loaded = await store.load_session("s1")
    assert loaded is not None and loaded.access_token == "api-at-secret"


async def test_pending_is_single_use_and_keyed_by_hash(store: Store) -> None:
    pending = PendingAuthorization(
        client_id="c", redirect_uri="http://x/cb", redirect_uri_provided_explicitly=True,
        code_challenge="ch", scopes=[], client_state="st", resource=None, google_code_verifier="v",
    )
    await store.save_pending("state-1", pending)
    assert await store.redis.ttl(PREFIX + "pending:" + hash_token("state-1")) <= 600
    assert await store.consume_pending("state-1") == pending
    assert await store.consume_pending("state-1") is None


async def test_code_single_use(store: Store) -> None:
    code = StoredCode(
        client_id="c", redirect_uri="http://x/cb", redirect_uri_provided_explicitly=True,
        code_challenge="ch", scopes=[], resource=None, sid="s1", user_id="42", expires_at=0,
    )
    await store.save_code("code-1", code)
    assert await store.redis.ttl(PREFIX + "code:" + hash_token("code-1")) <= 300
    assert await store.load_code("code-1") == code
    assert await store.consume_code("code-1") == code
    assert await store.consume_code("code-1") is None


async def test_tokens_hashed_indexed_and_cascade_deleted(store: Store) -> None:
    await store.save_session("s1", _session())
    exp = int(datetime.now(UTC).timestamp()) + 3600
    tok = StoredToken(client_id="c", sid="s1", user_id="42", scopes=[], resource=None, expires_at=exp)
    await store.save_token("at", "access-1", tok)
    await store.save_token("rt", "refresh-1", tok)
    keys = [k.decode() for k in await store.redis.keys("*")]
    assert not any("access-1" in k or "refresh-1" in k for k in keys)
    assert await store.load_token("at", "access-1") == tok
    await store.delete_session_cascade("s1")
    assert await store.load_token("at", "access-1") is None
    assert await store.load_token("rt", "refresh-1") is None
    assert await store.load_session("s1") is None


async def test_refresh_lock(store: Store) -> None:
    assert await store.acquire_refresh_lock("s1", "a")
    assert not await store.acquire_refresh_lock("s1", "b")
    await store.release_refresh_lock("s1", "b")  # not the owner: no effect
    assert not await store.acquire_refresh_lock("s1", "b")
    await store.release_refresh_lock("s1", "a")
    assert await store.acquire_refresh_lock("s1", "b")
