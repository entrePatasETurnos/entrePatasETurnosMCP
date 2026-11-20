"""The caller's own pets: ``GET /v1/pets``."""

from __future__ import annotations

from typing import Any

from .client import ApiClient


async def list_pets(client: ApiClient, token: str, *, page: int, size: int) -> Any:
    return await client._get("/v1/pets", token=token, params={"page": page, "size": size})
