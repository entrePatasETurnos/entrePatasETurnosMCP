"""Google sign-in for the MCP authorization flow (research R3, steps 2-3)."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL, not a secret


class GoogleSignInError(Exception):
    """Google refused the code exchange or returned no ID token."""


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class GoogleClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._http = httpx.AsyncClient(timeout=10.0, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    def authorize_url(self, state: str, code_challenge: str) -> str:
        query = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": self._settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange_code(self, code: str, code_verifier: str) -> str:
        """Exchange Google's authorization code for an ID token (verified later by the API)."""
        try:
            response = await self._http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret.get_secret_value(),
                    "redirect_uri": self._settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            logger.warning("google token exchange failed", extra={"error": type(exc).__name__})
            raise GoogleSignInError("google unreachable") from None
        if response.status_code != 200:
            logger.warning("google token exchange rejected", extra={"status": response.status_code})
            raise GoogleSignInError("google rejected the code")
        try:
            id_token = response.json().get("id_token")
        except ValueError:
            id_token = None
        if not isinstance(id_token, str) or not id_token:
            raise GoogleSignInError("no id_token in google response")
        return id_token
