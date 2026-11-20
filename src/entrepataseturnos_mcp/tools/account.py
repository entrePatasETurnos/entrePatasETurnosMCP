"""``sign_out`` - end the user's EntrePatasETurnos session (User Story 5)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools import Tool

from ..auth.session import current_session_id
from ..services import Services
from .confirm import write_tool
from .models import WriteInput


class SignOutInput(WriteInput):
    pass


def build_account_tools(services: Services) -> list[Tool]:
    async def sign_out(inp: SignOutInput, ctx: Context) -> dict[str, Any]:
        await services.sessions.sign_out(current_session_id())
        return {"signed_out": True}

    return [
        write_tool(
            name="sign_out",
            title="Sign out",
            description=(
                "Sign out of EntrePatasETurnos. Ends the session; the user must sign in again to "
                "use the other tools."
            ),
            input_model=SignOutInput,
            summarize=lambda inp: {"action": "sign out of EntrePatasETurnos"},
            action=sign_out,
        )
    ]
