"""User confirmation for write tools and the strict tool builders (research R8, Principle IV).

How confirmation works:

* If the client can show an elicitation prompt, the server asks the *user* directly before the
  tool body runs. Anything but an explicit ``confirm=true`` cancels, and the API is not called.
* Otherwise the tool requires ``user_confirmed: true`` in its input, and the description tells the
  assistant to show the details and get an explicit "yes" first.

Note: this module intentionally does NOT use ``from __future__ import annotations``. The SDK reads
the ``Annotated[..., Resolve(resolver)]`` parameter at runtime, and ``resolver`` is a closure.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from mcp_types import ToolAnnotations
from mcp_types.version import is_version_at_least
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import to_tool_error, tool_error
from .models import StrictInput, WriteInput

logger = logging.getLogger(__name__)

MODERN_PROTOCOL = "2026-07-28"


class Confirm(BaseModel):
    confirm: bool = Field(description="Confirm and submit this request?")


class NoElicitation:
    """Resolver result meaning "no prompt was shown"; the ``user_confirmed`` fallback applies."""


Outcome = (
    AcceptedElicitation[Confirm] | DeclinedElicitation | CancelledElicitation | NoElicitation
)


class _RawArgs(ArgModelBase):
    """Pass the caller's arguments through untouched so the tool validates them itself.

    This keeps rejected values (which may be passwords) out of error messages, rejects unknown
    fields, and lets every tool return the documented ``validation_error`` payload.
    """

    model_config = ConfigDict(extra="allow")

    def model_dump_one_level(self) -> dict[str, Any]:
        return {"raw": dict(self.model_extra or {})}


def client_can_elicit(ctx: Context) -> bool:
    session = ctx.request_context.session
    caps = session.client_capabilities
    if caps is None or caps.elicitation is None:
        return False
    try:
        modern = is_version_at_least(session.protocol_version, MODERN_PROTOCOL)
    except ValueError:
        modern = False
    # Modern protocol: the SDK returns an InputRequiredResult and the client retries.
    # Legacy protocol: needs a live back-channel on this request.
    return modern or session.can_send_request


def confirmation_message(title: str, summary: dict[str, Any]) -> str:
    lines = [f"Please confirm: {title}"]
    lines += [f"- {key}: {value}" for key, value in summary.items()]
    return "\n".join(lines)


def check_confirmation(outcome: Any, user_confirmed: bool | None, summary: dict[str, Any]) -> None:
    """Raise unless the user confirmed, either through the prompt or the fallback flag."""
    if isinstance(outcome, AcceptedElicitation) and isinstance(outcome.data, NoElicitation):
        outcome = outcome.data  # the SDK wraps plain resolver values as "accepted"
    if isinstance(outcome, NoElicitation):
        if user_confirmed is True:
            return
        raise tool_error(
            "confirmation_required",
            "Show these details to the user, ask for explicit confirmation, and call again with "
            "user_confirmed=true only if they agree.",
            details={"summary": summary},
        )
    if isinstance(outcome, AcceptedElicitation) and isinstance(outcome.data, Confirm):
        if outcome.data.confirm:
            return
    raise tool_error("cancelled_by_user", "The user did not confirm; nothing was submitted.")


def _validate[M: StrictInput](model: type[M], raw: dict[str, Any]) -> M:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise to_tool_error(exc) from None  # type: ignore[misc]  # always maps


async def _run(action: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    try:
        return await action()
    except Exception as exc:
        mapped = to_tool_error(exc)
        if mapped is None:
            raise
        raise mapped from None


def _finish(tool: Tool, input_model: type[StrictInput]) -> Tool:
    schema = input_model.model_json_schema()
    schema.setdefault("additionalProperties", False)
    metadata = tool.fn_metadata.model_copy(update={"arg_model": _RawArgs})
    return tool.model_copy(update={"parameters": schema, "fn_metadata": metadata})


def read_tool[M: StrictInput](
    *,
    name: str,
    title: str,
    description: str,
    input_model: type[M],
    action: Callable[[M, Context], Awaitable[dict[str, Any]]],
) -> Tool:
    async def handler(raw: dict[str, Any], ctx: Context) -> dict[str, Any]:
        inp = _validate(input_model, raw)
        return await _run(lambda: action(inp, ctx))

    tool = Tool.from_function(
        handler,
        name=name,
        title=title,
        description=f"{description}\n\nRead-only: does not change any data.",
        annotations=ToolAnnotations(
            title=title, read_only_hint=True, destructive_hint=False, open_world_hint=False
        ),
    )
    return _finish(tool, input_model)


def write_tool[W: WriteInput](
    *,
    name: str,
    title: str,
    description: str,
    input_model: type[W],
    summarize: Callable[[W], dict[str, Any]],
    action: Callable[[W, Context], Awaitable[dict[str, Any]]],
    destructive: bool = False,
) -> Tool:
    async def resolve_confirmation(raw: dict[str, Any], ctx: Context) -> Any:
        try:
            inp = input_model.model_validate(raw)
        except ValidationError:
            return NoElicitation()  # the body reports the validation error; never prompt for it
        if not client_can_elicit(ctx):
            return NoElicitation()
        return Elicit(confirmation_message(title, summarize(inp)), Confirm)

    async def handler(
        raw: dict[str, Any],
        ctx: Context,
        confirmation: Annotated[Outcome, Resolve(resolve_confirmation)],
    ) -> dict[str, Any]:
        inp = _validate(input_model, raw)
        check_confirmation(confirmation, inp.user_confirmed, summarize(inp))
        return await _run(lambda: action(inp, ctx))

    tool = Tool.from_function(
        handler,
        name=name,
        title=title,
        description=(
            f"{description}\n\nChanges data. Before calling, show the user the exact details "
            "and get their explicit confirmation. The client may also ask the user to confirm."
        ),
        annotations=ToolAnnotations(
            title=title,
            read_only_hint=False,
            destructive_hint=destructive,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    return _finish(tool, input_model)
