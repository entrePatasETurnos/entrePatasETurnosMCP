"""T047: startup fails fast on bad configuration without leaking secrets."""

import pytest

from entrepataseturnos_mcp.__main__ import main
from tests.unit.test_config import REQUIRED, env  # noqa: F401 - fixture


def test_missing_api_url_exits_2_naming_variable(env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    env.delenv("MCP_API_BASE_URL")
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "MCP_API_BASE_URL" in err
    for name in ("MCP_GOOGLE_CLIENT_SECRET", "MCP_REDIS_URL", "MCP_TOKEN_ENCRYPTION_KEY"):
        assert REQUIRED[name] not in err
