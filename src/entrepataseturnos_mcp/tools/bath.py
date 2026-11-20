"""Bath appointment tools (User Story 2, contracts/mcp-tools.md)."""

from __future__ import annotations

from typing import Any, Literal, Self

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools import Tool
from pydantic import Field, model_validator

from ..api import baths as api_baths
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

AppointmentStatus = Literal["registered", "approved", "denied", "completed"]


class BathSlotsInput(StrictInput):
    day: LocalDate = Field(alias="date", description="Day to check (YYYY-MM-DD)")


class AppointmentInput(WriteInput):
    pet_id: PositiveId = Field(description="Id of one of the user's own pets")
    starts_at: OffsetDateTime = Field(
        description="Slot start exactly as returned by get_bath_slots (with offset)"
    )

    @model_validator(mode="after")
    def _future(self) -> Self:
        not_in_past(self.starts_at, "starts_at")
        return self


class AppointmentUpdateInput(AppointmentInput):
    appointment_id: PositiveId


class AppointmentListInput(PageInput):
    status: AppointmentStatus | None = None
    from_: OffsetDateTime | None = Field(default=None, alias="from")
    to: OffsetDateTime | None = None


class AppointmentRefInput(StrictInput):
    appointment_id: PositiveId


class AppointmentCancelInput(WriteInput):
    appointment_id: PositiveId


def appointment_view(body: dict[str, Any]) -> dict[str, Any]:
    pet = body.get("pet") or {}
    view = {
        "id": body.get("id"),
        "status": body.get("status"),
        "starts_at": body.get("startsAt"),
        "ends_at": body.get("endsAt"),
        "pet": {"id": pet.get("id"), "name": pet.get("name")},
    }
    review = body.get("review") or {}
    if body.get("status") == "denied" and review.get("denialReason"):
        view["denial_reason"] = review["denialReason"]
    return view


def day_view(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": body.get("date"),
        "open": body.get("open"),
        "duration": body.get("duration"),
        "slots": [
            {
                "time": s.get("time"),
                "starts_at": s.get("startsAt"),
                "ends_at": s.get("endsAt"),
                "available": s.get("available"),
            }
            for s in body.get("slots") or []
        ],
    }


def appointment_summary(inp: AppointmentInput) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if isinstance(inp, AppointmentUpdateInput):
        summary["appointment"] = inp.appointment_id
    summary |= {"pet (id)": inp.pet_id, "bath starts at": inp.starts_at.isoformat()}
    return summary


def build_bath_tools(services: Services) -> list[Tool]:
    api = services.api

    async def slots(inp: BathSlotsInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(lambda t: api_baths.slots(api, t, day=inp.day))
        return day_view(body)

    async def create(inp: AppointmentInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_baths.create(api, t, pet_id=inp.pet_id, starts_at=inp.starts_at)
        )
        return appointment_view(body)

    async def list_mine(inp: AppointmentListInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_baths.list_mine(
                api, t, status=inp.status, from_=inp.from_, to=inp.to, page=inp.page, size=inp.size
            )
        )
        return {
            "items": [appointment_view(i) for i in body.get("items", [])],
            "page": PageInfo.from_api(body.get("page", {})).model_dump(),
        }

    async def get_one(inp: AppointmentRefInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(lambda t: api_baths.get(api, t, inp.appointment_id))
        return appointment_view(body)

    async def update(inp: AppointmentUpdateInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda t: api_baths.update(
                api, t, inp.appointment_id, pet_id=inp.pet_id, starts_at=inp.starts_at
            )
        )
        return appointment_view(body)

    async def cancel(inp: AppointmentCancelInput, ctx: Context) -> dict[str, Any]:
        await services.as_user(lambda t: api_baths.delete(api, t, inp.appointment_id))
        return {"cancelled": True, "appointment_id": inp.appointment_id}

    return [
        read_tool(
            name="get_bath_slots",
            title="Bath slots for a day",
            description=(
                "Show the bath slots for a day and whether each is available. Baths take one hour; "
                "the facility is closed on Sundays (open=false)."
            ),
            input_model=BathSlotsInput,
            action=slots,
        ),
        write_tool(
            name="create_bath_appointment",
            title="Schedule a bath",
            description=(
                "Schedule a bath for one of the signed-in user's pets. starts_at must exactly "
                "match an available slot from get_bath_slots."
            ),
            input_model=AppointmentInput,
            summarize=appointment_summary,
            action=create,
        ),
        read_tool(
            name="list_my_bath_appointments",
            title="List my bath appointments",
            description="List the signed-in user's bath appointments.",
            input_model=AppointmentListInput,
            action=list_mine,
        ),
        read_tool(
            name="get_bath_appointment",
            title="Get a bath appointment",
            description="Show one of the signed-in user's bath appointments.",
            input_model=AppointmentRefInput,
            action=get_one,
        ),
        write_tool(
            name="update_bath_appointment",
            title="Reschedule a bath",
            description=(
                "Change the pet or slot of one of the user's bath appointments. Only appointments "
                "still awaiting review (status 'registered') can be changed."
            ),
            input_model=AppointmentUpdateInput,
            summarize=appointment_summary,
            action=update,
        ),
        write_tool(
            name="cancel_bath_appointment",
            title="Cancel a bath appointment",
            description=(
                "Cancel (delete) one of the user's bath appointments. Only appointments still "
                "awaiting review (status 'registered') can be cancelled. This cannot be undone."
            ),
            input_model=AppointmentCancelInput,
            summarize=lambda inp: {"cancel bath appointment": inp.appointment_id},
            action=cancel,
            destructive=True,
        ),
    ]
