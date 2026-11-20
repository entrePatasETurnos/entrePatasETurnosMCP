"""Registration: ``POST /v1/users`` (public, never sends a user token)."""

from __future__ import annotations

from typing import Any

from .client import ApiClient


async def register(client: ApiClient, *, email: str, name: str, cpf: str, password: str) -> Any:
    return await client._post(
        "/v1/users", json={"email": email, "name": name, "cpf": cpf, "password": password}
    )
