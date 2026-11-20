"""Accommodation booking tools (User Story 1, contracts/mcp-tools.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Self

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools import Tool
from pydantic import Field, model_validator

from ..api import bookings as api_bookings
from ..services import Services
from .confirm import read_tool, write_tool
from .models import (
    LocalDate,
    OffsetDateTime,
    PageInfo,
    PageInput,
    PositiveId,
    StrictInput,
    WriteInput,
    not_in_past,
)

MAX_RANGE_DAYS = 366
BookingStatus = Literal["registered", "approved", "denied", "completed"]


# --------------------------------------------------------------------------- inputs


class FreeDatesInput(StrictInput):
    from_date: LocalDate | None = Field(
        default=None, description="First day to check (YYYY-MM-DD). Defaults to today."
    )
    to_date: LocalDate | None = Field(
        default=None, description="Last day to check (YYYY-MM-DD). Defaults to 29 days later."
    )
    pets: int = Field(default=1, ge=1, le=50, strict=True, description="Number of pets (1-50)")
    nights: int = Field(default=1, ge=1, le=90, strict=True, description="Nights of stay (1-90)")

    @model_validator(mode="after")
    def _range(self) -> Self:
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
        if self.from_date is not None and self.from_date < yesterday:
            raise ValueError("from_date must not be in the past")
        start = self.from_date or datetime.now(UTC).date()
        if self.to_date is not None:
            if self.to_date < start:
                raise ValueError("to_date must not be before from_date")
            if (self.to_date - start).days > MAX_RANGE_DAYS:
                raise ValueError(f"the date range must be at most {MAX_RANGE_DAYS} days")
        return self


class AvailabilityInput(StrictInput):
    from_: OffsetDateTime = Field(alias="from")
    to: OffsetDateTime

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.to <= self.from_:
            raise ValueError("'to' must be after 'from'")
        if self.to - self.from_ > timedelta(days=MAX_RANGE_DAYS):
            raise ValueError(f"the period must be at most {MAX_RANGE_DAYS} days")
        return self


class BookingInput(WriteInput):
    pet_ids: list[PositiveId] = Field(
        min_length=1, max_length=50, description="Ids of the user's own pets (1-50, no repeats)"
    )
    check_in: OffsetDateTime
    check_out: OffsetDateTime

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if len(set(self.pet_ids)) != len(self.pet_ids):
            raise ValueError("pet_ids must not contain duplicates")
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        not_in_past(self.check_in, "check_in")
        return self


class BookingUpdateInput(BookingInput):
    booking_id: PositiveId


class BookingListInput(PageInput):
    status: BookingStatus | None = None
    from_: OffsetDateTime | None = Field(default=None, alias="from")
    to: OffsetDateTime | None = None


class BookingRefInput(StrictInput):
    booking_id: PositiveId


class BookingCancelInput(WriteInput):
    booking_id: PositiveId


# -------------------------------------------------------------------------- outputs


def booking_view(body: dict[str, Any]) -> dict[str, Any]:
    view = {
        "id": body.get("id"),
        "status": body.get("status"),
        "check_in": body.get("checkIn"),
        "check_out": body.get("checkOut"),
        "nights": body.get("nights"),
        "pets": [{"id": p.get("id"), "name": p.get("name")} for p in body.get("pets") or []],
    }
    review = body.get("review") or {}
    if body.get("status") == "denied" and review.get("denialReason"):
        view["denial_reason"] = review["denialReason"]
    return view


def free_dates_view(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": body.get("from"),
        "to": body.get("to"),
        "pets": body.get("pets"),
        "nights": body.get("nights"),
        "first_fit": body.get("firstFit"),
        "days": [
            {"date": d.get("date"), "free": d.get("free"), "fits": d.get("fits")}
            for d in body.get("days") or []
        ],
    }


def availability_view(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": body.get("from"),
        "to": body.get("to"),
        "capacity": body.get("capacity"),
        "intervals": [
            {"start": i.get("start"), "end": i.get("end"), "available": i.get("available")}
            for i in body.get("intervals") or []
        ],
    }


def _nights(check_in: datetime, check_out: datetime) -> int:
    local_out = check_out.astimezone(check_in.tzinfo)
    return max(1, (local_out.date() - check_in.date()).days)


def booking_summary(inp: BookingInput) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if isinstance(inp, BookingUpdateInput):
        summary["booking"] = inp.booking_id
    summary |= {
        "pets (ids)": ", ".join(str(p) for p in inp.pet_ids),
        "check-in": inp.check_in.isoformat(),
        "check-out": inp.check_out.isoformat(),
        "nights (approx.)": _nights(inp.check_in, inp.check_out),
    }
    return summary


# ---------------------------------------------------------------------------- tools


def build_accommodation_tools(services: Services) -> list[Tool]:
    api = services.api

    async def free_dates(inp: FreeDatesInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_bookings.free_dates(
                api, t, from_date=inp.from_date, to_date=inp.to_date, pets=inp.pets, nights=inp.nights
            )
        )
        return free_dates_view(body)

    async def availability(inp: AvailabilityInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_bookings.availability(api, t, from_=inp.from_, to=inp.to)
        )
        return availability_view(body)

    async def create(inp: BookingInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_bookings.create(
                api, t, pet_ids=inp.pet_ids, check_in=inp.check_in, check_out=inp.check_out
            )
        )
        return booking_view(body)

    async def list_mine(inp: BookingListInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_bookings.list_mine(
                api, t, status=inp.status, from_=inp.from_, to=inp.to, page=inp.page, size=inp.size
            )
        )
        return {
            "items": [booking_view(i) for i in body.get("items", [])],
            "page": PageInfo.from_api(body.get("page", {})).model_dump(),
        }

    async def get_one(inp: BookingRefInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(lambda t: api_bookings.get(api, t, inp.booking_id))
        return booking_view(body)

    async def update(inp: BookingUpdateInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_bookings.update(
                api,
                t,
                inp.booking_id,
                pet_ids=inp.pet_ids,
                check_in=inp.check_in,
                check_out=inp.check_out,
            )
        )
        return booking_view(body)

    async def cancel(inp: BookingCancelInput, ctx: Context) -> dict[str, Any]:
        await services.as_user(lambda t: api_bookings.delete(api, t, inp.booking_id))
        return {"cancelled": True, "booking_id": inp.booking_id}

    return [
        read_tool(
            name="get_accommodation_free_dates",
            title="Find free accommodation dates",
            description=(
                "Show, day by day, whether the facility can host the given number of pets for the "
                "given number of nights starting on each day. Use before booking a stay."
            ),
            input_model=FreeDatesInput,
            action=free_dates,
        ),
        read_tool(
            name="get_accommodation_availability",
            title="Accommodation availability",
            description="Show free accommodation places per time interval for a period.",
            input_model=AvailabilityInput,
            action=availability,
        ),
        write_tool(
            name="create_accommodation_booking",
            title="Book accommodation",
            description=(
                "Book an accommodation stay for some of the signed-in user's pets. The booking "
                "starts with status 'registered' and is reviewed by the staff."
            ),
            input_model=BookingInput,
            summarize=booking_summary,
            action=create,
        ),
        read_tool(
            name="list_my_accommodation_bookings",
            title="List my bookings",
            description="List the signed-in user's accommodation bookings, newest first.",
            input_model=BookingListInput,
            action=list_mine,
        ),
        read_tool(
            name="get_accommodation_booking",
            title="Get a booking",
            description="Show one of the signed-in user's accommodation bookings.",
            input_model=BookingRefInput,
            action=get_one,
        ),
        write_tool(
            name="update_accommodation_booking",
            title="Change a booking",
            description=(
                "Change the pets or dates of one of the user's bookings. Only bookings still "
                "awaiting review (status 'registered') can be changed."
            ),
            input_model=BookingUpdateInput,
            summarize=booking_summary,
            action=update,
        ),
        write_tool(
            name="cancel_accommodation_booking",
            title="Cancel a booking",
            description=(
                "Cancel (delete) one of the user's bookings. Only bookings still awaiting review "
                "(status 'registered') can be cancelled. This cannot be undone."
            ),
            input_model=BookingCancelInput,
            summarize=lambda inp: {"cancel booking": inp.booking_id},
            action=cancel,
            destructive=True,
        ),
    ]
