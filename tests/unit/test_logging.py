import json
import logging

from entrepataseturnos_mcp.logging import REDACTED, JsonFormatter, redact


def _format(msg: str, **extra: object) -> dict:
    record = logging.makeLogRecord({"name": "t", "levelname": "INFO", "msg": msg})
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonFormatter().format(record))


def test_sensitive_keys_are_redacted_case_insensitively_and_nested() -> None:
    out = redact(
        {
            "Authorization": "Bearer x",
            "password": "p",
            "CPF": "123",
            "idToken": "g",
            "code": "c",
            "client_secret": "s",
            "nested": {"access_token": "a", "refreshToken": "r", "ok": 1},
            "items": [{"token": "t"}],
            "status": "fine",
            "error_code": "kept",
        }
    )
    assert out["Authorization"] == out["password"] == out["CPF"] == REDACTED
    assert out["idToken"] == out["code"] == out["client_secret"] == REDACTED
    assert out["nested"] == {"access_token": REDACTED, "refreshToken": REDACTED, "ok": 1}
    assert out["items"] == [{"token": REDACTED}]
    assert out["status"] == "fine" and out["error_code"] == "kept"


def test_formatter_redacts_extras_and_bearer_in_messages() -> None:
    data = _format("calling with Bearer abc.def-123", password="hunter22", api_status=200)
    assert "abc.def-123" not in json.dumps(data)
    assert data["password"] == REDACTED
    assert data["api_status"] == 200
