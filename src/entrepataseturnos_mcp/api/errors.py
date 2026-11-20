"""Errors raised by the EntrePatasETurnos API client."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """The API answered with an error status (or an unusable body)."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        fields: dict[str, str] | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}
        self.extras = extras or {}


class UpstreamTimeout(Exception):
    """A read request timed out."""


class OutcomeUnknown(Exception):
    """A write request timed out: the API may or may not have applied it."""


class UpstreamUnavailable(Exception):
    """The API could not be reached."""
