"""The two MCP servers (research R9).

* ``/mcp`` - OAuth-protected; acts as the signed-in user. 15 tools.
* ``/public/mcp`` - unauthenticated; exactly one tool, ``register_account``.

No pet-training tool exists (FR-003); the catalogue is pinned by tests/contract/test_tool_catalogue.py.
"""

from __future__ import annotations

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.request_state import RequestStateSecurity

from . import __version__
from .api.client import ApiClient
from .auth.crypto import derive_key
from .auth.provider import RedisOAuthProvider
from .config import Settings
from .services import Services
from .tools.accommodation import build_accommodation_tools
from .tools.account import build_account_tools
from .tools.bath import build_bath_tools
from .tools.pets import build_pet_tools
from .tools.registration import build_registration_tools

INSTRUCTIONS = (
    "Tools for EntrePatasETurnos pet services: the signed-in user's pets, accommodation bookings "
    "and bath appointments. Before any tool that changes data, show the user the exact details and "
    "get explicit confirmation. Times must include a UTC offset; the facility is in "
    "America/Sao_Paulo. Never invent results: report API errors as returned."
)
PUBLIC_INSTRUCTIONS = (
    "Account registration for EntrePatasETurnos. Confirm the details with the user before "
    "submitting, and never repeat the password back."
)


def _request_state(settings: Settings) -> RequestStateSecurity:
    # Shared across replicas so a multi-round (elicitation) call can resume on any instance.
    return RequestStateSecurity(keys=[derive_key(settings.encryption_key_bytes, "request-state")])


def build_authenticated_server(
    settings: Settings, provider: RedisOAuthProvider, services: Services
) -> MCPServer:
    tools = [
        *build_pet_tools(services),
        *build_accommodation_tools(services),
        *build_bath_tools(services),
        *build_account_tools(services),
    ]
    server: MCPServer = MCPServer(
        name="entrepataseturnos",
        title="EntrePatasETurnos",
        instructions=INSTRUCTIONS,
        version=__version__,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.public_base_url,  # type: ignore[arg-type]  # pydantic coerces
            resource_server_url=provider.resource_url,  # type: ignore[arg-type]
            validate_token_resource=True,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
        tools=tools,
        request_state_security=_request_state(settings),
    )
    server.custom_route("/oauth/google/callback", methods=["GET"], include_in_schema=False)(
        provider.handle_google_callback
    )
    return server


def build_public_server(settings: Settings, api: ApiClient) -> MCPServer:
    return MCPServer(
        name="entrepataseturnos-public",
        title="EntrePatasETurnos registration",
        instructions=PUBLIC_INSTRUCTIONS,
        version=__version__,
        tools=build_registration_tools(api),
        request_state_security=_request_state(settings),
    )
