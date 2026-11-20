"""Runtime configuration, read from ``MCP_*`` environment variables (data-model.md §1)."""

from __future__ import annotations

import base64
import binascii
import sys
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Settings(BaseSettings):
    """Validated settings. Secret values are ``SecretStr`` and never appear in ``repr``."""

    model_config = SettingsConfigDict(env_prefix="MCP_", extra="ignore", hide_input_in_errors=True)

    api_base_url: str
    api_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    public_base_url: str
    google_client_id: str = Field(min_length=1)
    google_client_secret: SecretStr
    redis_url: SecretStr
    token_encryption_key: SecretStr
    access_token_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    allowed_hosts: str = ""
    host: str = "0.0.0.0"  # noqa: S104 - container must listen on all interfaces
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("api_base_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("must be an http(s) URL")
        return value.rstrip("/")

    @field_validator("public_base_url")
    @classmethod
    def _public_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if not parts.hostname:
            raise ValueError("must be an absolute URL")
        if parts.scheme != "https" and not (
            parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
        ):
            raise ValueError("must use https (http is allowed only for localhost)")
        return value.rstrip("/")

    @field_validator("token_encryption_key")
    @classmethod
    def _key_is_32_bytes(cls, value: SecretStr) -> SecretStr:
        try:
            raw = base64.b64decode(value.get_secret_value(), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("must be base64") from exc
        if len(raw) != 32:
            raise ValueError("must decode to exactly 32 bytes")
        return value

    @field_validator("google_client_secret", "redis_url")
    @classmethod
    def _not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.b64decode(self.token_encryption_key.get_secret_value())

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url}/oauth/google/callback"

    @property
    def allowed_host_list(self) -> list[str]:
        public = urlsplit(self.public_base_url)
        hosts = {public.netloc, "localhost", "127.0.0.1", "localhost:*", "127.0.0.1:*"}
        if public.hostname:
            hosts.add(f"{public.hostname}:*")
        hosts.update(h.strip() for h in self.allowed_hosts.split(",") if h.strip())
        return sorted(hosts)


def describe_errors(exc: ValidationError) -> list[str]:
    """One line per failing setting, naming the variable but never its value."""
    lines = []
    for error in exc.errors(include_input=False):
        field = str(error["loc"][0]) if error["loc"] else "?"
        lines.append(f"missing/invalid setting: MCP_{field.upper()} ({error['msg']})")
    return lines


def load_settings() -> Settings:
    """Load settings or exit with status 2, naming each bad variable without printing values."""
    try:
        return Settings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        for line in describe_errors(exc):
            print(line, file=sys.stderr)
        raise SystemExit(2) from None
