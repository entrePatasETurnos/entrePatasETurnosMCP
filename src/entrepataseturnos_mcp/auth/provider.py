"""OAuth 2.1 authorization server for MCP clients, federating sign-in to Google (research R3).

Flow: client ``/authorize`` -> Google -> ``/oauth/google/callback`` -> API session -> MCP code
-> client ``/token``. Clients only ever receive opaque MCP tokens; API and Google tokens stay
server-side.
"""

from __future__ import annotations

import logging
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from ..api.errors import ApiError, OutcomeUnknown, UpstreamTimeout, UpstreamUnavailable
from ..config import Settings
from .crypto import new_token
from .errors import SessionStoreUnavailable, SignInRequired
from .google import GoogleClient, GoogleSignInError, pkce_pair
from .session import SessionService
from .store import CODE_TTL, PendingAuthorization, Store, StoredCode, StoredToken

logger = logging.getLogger(__name__)


class SessionAuthorizationCode(AuthorizationCode):
    sid: str


class SessionRefreshToken(RefreshToken):
    sid: str


class RedisOAuthProvider:
    """Implements ``OAuthAuthorizationServerProvider`` on top of :class:`Store`."""

    def __init__(
        self, settings: Settings, store: Store, sessions: SessionService, google: GoogleClient
    ) -> None:
        self._settings = settings
        self._store = store
        self._sessions = sessions
        self._google = google
        self.resource_url = f"{settings.public_base_url}/mcp"

    def _check_resource(self, resource: str | None) -> None:
        if resource is not None and resource.rstrip("/") != self.resource_url:
            raise AuthorizeError("invalid_target", "this server only issues tokens for its /mcp endpoint")

    # ---------------------------------------------------------------- client registration
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = await self._store.load_client(client_id)
        return None if data is None else OAuthClientInformationFull.model_validate(data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if client_info.client_id is None:
            raise ValueError("client_id is required")
        await self._store.save_client(
            client_info.client_id, client_info.model_dump(mode="json", exclude_none=True)
        )

    # ---------------------------------------------------------------------- authorize
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        assert client.client_id is not None
        self._check_resource(params.resource)
        state = new_token()
        verifier, challenge = pkce_pair()
        await self._store.save_pending(
            state,
            PendingAuthorization(
                client_id=client.client_id,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                code_challenge=params.code_challenge,
                scopes=params.scopes or [],
                client_state=params.state,
                resource=params.resource,
                google_code_verifier=verifier,
            ),
        )
        return self._google.authorize_url(state, challenge)

    async def handle_google_callback(self, request: Request) -> Response:
        """``GET /oauth/google/callback``: finish Google sign-in and hand an MCP code to the client."""
        state = request.query_params.get("state")
        if not state:
            return PlainTextResponse("Missing state.", status_code=400)
        try:
            pending = await self._store.consume_pending(state)
        except SessionStoreUnavailable:
            return PlainTextResponse("Service temporarily unavailable.", status_code=503)
        if pending is None:
            return PlainTextResponse(
                "This sign-in link is invalid or has expired. Start again from your assistant.",
                status_code=400,
            )

        def back(error: str, description: str) -> RedirectResponse:
            url = construct_redirect_uri(
                pending.redirect_uri,
                error=error,
                error_description=description,
                state=pending.client_state,
            )
            return RedirectResponse(url, status_code=302)

        if request.query_params.get("error"):
            return back("access_denied", "Google sign-in was cancelled or refused.")
        code = request.query_params.get("code")
        if not code:
            return back("invalid_request", "Google did not return an authorization code.")

        try:
            id_token = await self._google.exchange_code(code, pending.google_code_verifier)
            sid, session = await self._sessions.create_from_google(id_token)
        except GoogleSignInError:
            return back("server_error", "Google sign-in could not be completed.")
        except ApiError as exc:
            logger.info("api rejected google sign-in", extra={"api_error": exc.code})
            if 400 <= exc.status < 500:
                return back("access_denied", f"{exc.code}: {exc.message}")
            return back("server_error", f"{exc.code}: {exc.message}")
        except (UpstreamUnavailable, UpstreamTimeout, OutcomeUnknown, SessionStoreUnavailable):
            return back("temporarily_unavailable", "The service is unavailable; try again later.")

        mcp_code = new_token()
        await self._store.save_code(
            mcp_code,
            StoredCode(
                client_id=pending.client_id,
                redirect_uri=pending.redirect_uri,
                redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
                code_challenge=pending.code_challenge,
                scopes=pending.scopes,
                resource=pending.resource,
                sid=sid,
                user_id=session.user_id,
                expires_at=time.time() + CODE_TTL,
            ),
        )
        url = construct_redirect_uri(pending.redirect_uri, code=mcp_code, state=pending.client_state)
        return RedirectResponse(url, status_code=302)

    # ------------------------------------------------------------------ authorization codes
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> SessionAuthorizationCode | None:
        stored = await self._store.load_code(authorization_code)
        if stored is None or stored.client_id != client.client_id:
            return None
        return SessionAuthorizationCode(
            code=authorization_code,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
            client_id=stored.client_id,
            code_challenge=stored.code_challenge,
            redirect_uri=stored.redirect_uri,  # type: ignore[arg-type]  # pydantic coerces
            redirect_uri_provided_explicitly=stored.redirect_uri_provided_explicitly,
            resource=stored.resource,
            subject=stored.user_id,
            sid=stored.sid,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: SessionAuthorizationCode
    ) -> OAuthToken:
        stored = await self._store.consume_code(authorization_code.code)  # single use
        if stored is None:
            raise TokenError("invalid_grant", "authorization code already used or expired")
        return await self._issue(stored.client_id, stored.sid, stored.user_id, stored.scopes, stored.resource)

    # -------------------------------------------------------------------- refresh tokens
    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> SessionRefreshToken | None:
        stored = await self._store.load_token("rt", refresh_token)
        if stored is None or stored.client_id != client.client_id:
            return None
        return SessionRefreshToken(
            token=refresh_token,
            client_id=stored.client_id,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
            resource=stored.resource,
            subject=stored.user_id,
            sid=stored.sid,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: SessionRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        await self._store.delete_token("rt", refresh_token.token, refresh_token.sid)  # rotate
        if await self._store.load_session(refresh_token.sid) is None:
            raise TokenError("invalid_grant", "the session has ended; sign in again")
        assert refresh_token.subject is not None
        return await self._issue(
            refresh_token.client_id,
            refresh_token.sid,
            refresh_token.subject,
            scopes or refresh_token.scopes,
            refresh_token.resource,
        )

    # --------------------------------------------------------------------- access tokens
    async def load_access_token(self, token: str) -> AccessToken | None:
        stored = await self._store.load_token("at", token)
        if stored is None:
            return None
        return AccessToken(
            token=token,
            client_id=stored.client_id,
            scopes=stored.scopes,
            expires_at=stored.expires_at,
            resource=stored.resource,
            subject=stored.user_id,
            claims={"sid": stored.sid, "iss": self._settings.public_base_url},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        sid = getattr(token, "sid", None) or (getattr(token, "claims", None) or {}).get("sid")
        if isinstance(sid, str):
            await self._sessions.sign_out(sid)

    async def exchange_identity_assertion(self, client: OAuthClientInformationFull, params: object) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "not supported")

    # --------------------------------------------------------------------------- helpers
    async def _issue(
        self, client_id: str, sid: str, user_id: str, scopes: list[str], resource: str | None
    ) -> OAuthToken:
        session = await self._store.load_session(sid)
        if session is None:
            raise SignInRequired("session missing")
        resource = self.resource_url  # we serve exactly one protected resource
        now = int(time.time())
        access_ttl = self._settings.access_token_ttl_seconds
        access, refresh = new_token(), new_token()
        await self._store.save_token(
            "at",
            access,
            StoredToken(
                client_id=client_id,
                sid=sid,
                user_id=user_id,
                scopes=scopes,
                resource=resource,
                expires_at=now + access_ttl,
            ),
        )
        await self._store.save_token(
            "rt",
            refresh,
            StoredToken(
                client_id=client_id,
                sid=sid,
                user_id=user_id,
                scopes=scopes,
                resource=resource,
                expires_at=int(session.refresh_expires_at.timestamp()),
            ),
        )
        return OAuthToken(
            access_token=access,
            expires_in=access_ttl,
            refresh_token=refresh,
            scope=" ".join(scopes) or None,
        )
