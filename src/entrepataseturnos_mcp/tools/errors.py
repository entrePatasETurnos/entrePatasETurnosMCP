"""Mapping of internal failures to the tool error payload (data-model.md §5)."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from ..api.errors import ApiError, OutcomeUnknown, UpstreamTimeout, UpstreamUnavailable
from ..auth.errors import SessionStoreUnavailable, SignInRequired

# API extras renamed to snake_case detail keys.
_EXTRA_RENAMES = {"petIds": "pet_ids", "petId": "pet_id"}


def payload(
    error_code: str,
    message: str,
    *,
    http_status: int | None = None,
    fields: dict[str, str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error_code": error_code, "message": message}
    if http_status is not None:
        body["http_status"] = http_status
    if fields:
        body["fields"] = fields
    if details:
        body["details"] = details
    return body


def tool_error(error_code: str, message: str, **kwargs: Any) -> ToolError:
    return ToolError(json.dumps(payload(error_code, message, **kwargs), ensure_ascii=False))


def validation_fields(exc: ValidationError) -> dict[str, str]:
    """Field path -> message. Rejected values are never included (they may be secrets)."""
    fields: dict[str, str] = {}
    for err in exc.errors(include_input=False, include_url=False, include_context=False):
        loc = ".".join(str(p) for p in err["loc"]) or "input"
        msg = err["msg"]
        if err["type"] == "extra_forbidden":
            msg = "unknown field; this tool does not accept it"
        fields.setdefault(loc, msg)
    return fields


def to_tool_error(exc: BaseException) -> ToolError | None:
    """Translate a known failure; return ``None`` for unexpected exceptions (they stay crashes)."""
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, ValidationError):
        return tool_error(
            "validation_error", "one or more inputs are invalid", fields=validation_fields(exc)
        )
    if isinstance(exc, ApiError):
        details = {_EXTRA_RENAMES.get(k, _snake(k)): v for k, v in exc.extras.items()}
        return tool_error(
            exc.code, exc.message, http_status=exc.status, fields=exc.fields, details=details
        )
    if isinstance(exc, OutcomeUnknown):
        return tool_error(
            "outcome_unknown",
            "The API did not confirm the result in time. The change may or may not have been "
            "applied; check the current state before trying again.",
        )
    if isinstance(exc, UpstreamTimeout):
        return tool_error("upstream_timeout", "The API did not answer in time; try again.")
    if isinstance(exc, UpstreamUnavailable):
        return tool_error("upstream_unavailable", "The API is unreachable; try again later.")
    if isinstance(exc, SignInRequired):
        return tool_error("sign_in_required", "Your session has ended. Please sign in again.")
    if isinstance(exc, SessionStoreUnavailable):
        return tool_error(
            "session_store_unavailable", "The service is temporarily unavailable; try again later."
        )
    return None


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
