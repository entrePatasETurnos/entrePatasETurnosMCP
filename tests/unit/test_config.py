import pytest
from pydantic import ValidationError

from entrepataseturnos_mcp.config import Settings, describe_errors
from tests.conftest import GOOGLE_SECRET, REDIS_PASSWORD, TEST_KEY

REQUIRED = {
    "MCP_API_BASE_URL": "http://api.test",
    "MCP_PUBLIC_BASE_URL": "https://mcp.example.com",
    "MCP_GOOGLE_CLIENT_ID": "gid",
    "MCP_GOOGLE_CLIENT_SECRET": GOOGLE_SECRET,
    "MCP_REDIS_URL": f"redis://:{REDIS_PASSWORD}@redis:6379/0",
    "MCP_TOKEN_ENCRYPTION_KEY": TEST_KEY,
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in list(__import__("os").environ):
        if key.startswith("MCP_"):
            monkeypatch.delenv(key)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_loads_with_all_required(env: pytest.MonkeyPatch) -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.api_base_url == "http://api.test"
    assert s.api_timeout_seconds == 10
    assert s.google_redirect_uri == "https://mcp.example.com/oauth/google/callback"
    assert len(s.encryption_key_bytes) == 32


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_each_missing_variable_is_named(env: pytest.MonkeyPatch, missing: str) -> None:
    env.delenv(missing)
    with pytest.raises(ValidationError) as exc:
        Settings()  # type: ignore[call-arg]
    lines = describe_errors(exc.value)
    assert any(missing in line for line in lines)


def test_secrets_never_in_repr_or_errors(env: pytest.MonkeyPatch) -> None:
    s = Settings()  # type: ignore[call-arg]
    text = repr(s) + str(s)
    for secret in (GOOGLE_SECRET, REDIS_PASSWORD, TEST_KEY):
        assert secret not in text
    env.setenv("MCP_TOKEN_ENCRYPTION_KEY", "not-base64-" + GOOGLE_SECRET)
    with pytest.raises(ValidationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert GOOGLE_SECRET not in "\n".join(describe_errors(exc.value))


def test_public_url_must_be_https_except_localhost(env: pytest.MonkeyPatch) -> None:
    env.setenv("MCP_PUBLIC_BASE_URL", "http://mcp.example.com")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
    env.setenv("MCP_PUBLIC_BASE_URL", "http://localhost:8000")
    assert Settings().public_base_url == "http://localhost:8000"  # type: ignore[call-arg]


def test_encryption_key_must_be_32_bytes(env: pytest.MonkeyPatch) -> None:
    import base64

    env.setenv("MCP_TOKEN_ENCRYPTION_KEY", base64.b64encode(b"short").decode())
    with pytest.raises(ValidationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert any("MCP_TOKEN_ENCRYPTION_KEY" in line for line in describe_errors(exc.value))


def test_allowed_hosts_include_public_host_and_extras(env: pytest.MonkeyPatch) -> None:
    env.setenv("MCP_ALLOWED_HOSTS", "mcp.internal, svc.cluster.local")
    hosts = Settings().allowed_host_list  # type: ignore[call-arg]
    assert {"mcp.example.com", "mcp.internal", "svc.cluster.local", "localhost:*"} <= set(hosts)
