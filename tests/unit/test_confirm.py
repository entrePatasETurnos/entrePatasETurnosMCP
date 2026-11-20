import json

import pytest
from mcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.server.mcpserver.exceptions import ToolError

from entrepataseturnos_mcp.tools.confirm import Confirm, NoElicitation, check_confirmation, confirmation_message

SUMMARY = {"check-in": "2026-12-01T14:00:00-03:00"}


def _code(exc: pytest.ExceptionInfo[ToolError]) -> dict:
    return json.loads(str(exc.value))


def test_accepted_true_proceeds() -> None:
    check_confirmation(AcceptedElicitation(data=Confirm(confirm=True)), None, SUMMARY)


@pytest.mark.parametrize(
    "outcome",
    [AcceptedElicitation(data=Confirm(confirm=False)), DeclinedElicitation(), CancelledElicitation()],
)
def test_anything_else_is_cancelled_by_user(outcome) -> None:
    with pytest.raises(ToolError) as exc:
        check_confirmation(outcome, True, SUMMARY)  # user_confirmed cannot override a refusal
    assert _code(exc)["error_code"] == "cancelled_by_user"


@pytest.mark.parametrize("outcome", [NoElicitation(), AcceptedElicitation.model_construct(data=NoElicitation())])
def test_fallback_requires_user_confirmed(outcome) -> None:
    check_confirmation(outcome, True, SUMMARY)
    for flag in (None, False):
        with pytest.raises(ToolError) as exc:
            check_confirmation(outcome, flag, SUMMARY)
        body = _code(exc)
        assert body["error_code"] == "confirmation_required"
        assert body["details"]["summary"] == SUMMARY


def test_message_lists_summary() -> None:
    msg = confirmation_message("Book accommodation", SUMMARY)
    assert msg.startswith("Please confirm: Book accommodation") and "check-in" in msg
