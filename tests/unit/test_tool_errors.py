import json

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, ValidationError

from entrepataseturnos_mcp.api.errors import ApiError, OutcomeUnknown, UpstreamTimeout, UpstreamUnavailable
from entrepataseturnos_mcp.auth.errors import SessionStoreUnavailable, SignInRequired
from entrepataseturnos_mcp.tools.errors import to_tool_error


def _p(err: ToolError | None) -> dict:
    assert err is not None
    return json.loads(str(err))


def test_api_error_payload_with_details_renamed() -> None:
    body = _p(to_tool_error(ApiError("pet_already_booked", "m", 409, extras={"petIds": [3]})))
    assert body == {"error_code": "pet_already_booked", "message": "m", "http_status": 409, "details": {"pet_ids": [3]}}
    body = _p(to_tool_error(ApiError("pet_already_scheduled", "m", 409, extras={"petId": 7})))
    assert body["details"] == {"pet_id": 7}


def test_fields_and_details_only_when_present() -> None:
    body = _p(to_tool_error(ApiError("invalid_request", "m", 400, fields={"cpf": "inválido"})))
    assert body["fields"] == {"cpf": "inválido"} and "details" not in body
    body = _p(to_tool_error(ApiError("booking_not_found", "m", 404)))
    assert "fields" not in body and "details" not in body


def test_validation_error_never_contains_input() -> None:
    class M(BaseModel):
        model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
        password: int

    try:
        M.model_validate({"password": "hunter2-secret", "user_id": 5})
    except ValidationError as exc:
        body = _p(to_tool_error(exc))
    assert body["error_code"] == "validation_error"
    assert set(body["fields"]) == {"password", "user_id"}
    assert "hunter2-secret" not in json.dumps(body)


def test_local_codes() -> None:
    assert _p(to_tool_error(OutcomeUnknown()))["error_code"] == "outcome_unknown"
    assert _p(to_tool_error(UpstreamTimeout()))["error_code"] == "upstream_timeout"
    assert _p(to_tool_error(UpstreamUnavailable()))["error_code"] == "upstream_unavailable"
    assert _p(to_tool_error(SignInRequired()))["error_code"] == "sign_in_required"
    assert _p(to_tool_error(SessionStoreUnavailable()))["error_code"] == "session_store_unavailable"
    assert to_tool_error(RuntimeError("x")) is None
