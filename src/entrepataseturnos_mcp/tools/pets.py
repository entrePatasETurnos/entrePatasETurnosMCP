"""``list_my_pets`` - the signed-in user's own pets (needed to pick pets for bookings/baths)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools import Tool

from ..api import pets as api_pets
from ..services import Services
from .confirm import read_tool
from .models import PageInfo, PageInput


class ListPetsInput(PageInput):
    pass


def pet_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item.get(k) for k in ("id", "name", "species", "gender", "age")}


def build_pet_tools(services: Services) -> list[Tool]:
    async def list_my_pets(inp: ListPetsInput, ctx: Context) -> dict[str, Any]:
        body = await services.as_user(
            lambda token: api_pets.list_pets(services.api, token, page=inp.page, size=inp.size)
        )
        return {
            "items": [pet_summary(i) for i in body.get("items", [])],
            "page": PageInfo.from_api(body.get("page", {})).model_dump(),
        }

    return [
        read_tool(
            name="list_my_pets",
            title="List my pets",
            description=(
                "List the signed-in user's own pets (id, name, species, gender, age). Use the pet "
                "ids when booking accommodation or scheduling a bath."
            ),
            input_model=ListPetsInput,
            action=list_my_pets,
        )
    ]
