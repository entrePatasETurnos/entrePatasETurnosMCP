"""Shared input/output types for tools (data-model.md §3-4)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")
FACILITY_TZ_HINT = "America/Sao_Paulo (e.g. -03:00)"


def _offset_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("must be an ISO-8601 date-time string")
    text = value.strip()
    if "T" not in text or not _OFFSET_RE.search(text):
        raise ValueError(
            "must be an ISO-8601 date-time with an explicit UTC offset, "
            f"e.g. 2026-12-01T14:00:00-03:00; the facility uses {FACILITY_TZ_HINT}"
        )
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("is not a valid ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError("must include a UTC offset")
    return parsed


def _local_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("is not a valid calendar date") from exc


OffsetDateTime = Annotated[
    datetime,
    BeforeValidator(_offset_datetime),
    Field(
        json_schema_extra={"type": "string", "format": "date-time"},
        description="ISO-8601 date-time with an explicit offset, e.g. 2026-12-01T14:00:00-03:00",
    ),
]
LocalDate = Annotated[
    date,
    BeforeValidator(_local_date),
    Field(json_schema_extra={"type": "string", "format": "date"}, description="Date as YYYY-MM-DD"),
]
PositiveId = Annotated[int, Field(ge=1, strict=True)]


class StrictInput(BaseModel):
    """Base for every tool input: unknown fields (including identity fields) are rejected."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class PageInput(StrictInput):
    page: int = Field(default=0, ge=0, strict=True, description="Zero-based page number")
    size: int = Field(default=20, ge=1, le=100, strict=True, description="Items per page (1-100)")


class WriteInput(StrictInput):
    user_confirmed: bool | None = Field(
        default=None,
        description=(
            "Only used when the client cannot show a confirmation prompt. Set to true ONLY "
            "after you have shown the user the exact details and they explicitly said yes."
        ),
    )


class PageInfo(BaseModel):
    number: int
    size: int
    total_items: int
    total_pages: int

    @classmethod
    def from_api(cls, page: dict[str, Any]) -> PageInfo:
        return cls(
            number=int(page.get("number", 0)),
            size=int(page.get("size", 0)),
            total_items=int(page.get("totalItems", 0)),
            total_pages=int(page.get("totalPages", 0)),
        )


def now() -> datetime:
    return datetime.now(UTC)


def not_in_past(value: datetime, field: str) -> None:
    if value < now():
        raise ValueError(f"{field} must not be in the past")


def iso(value: datetime) -> str:
    """Serialize keeping the caller's UTC offset."""
    return value.isoformat()
