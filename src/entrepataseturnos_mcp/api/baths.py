"""Bath appointments: ``/v1/bath-appointments`` (API spec 032)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .client import ApiClient

BASE = "/v1/bath-appointments"


async def slots(client: ApiClient, token: str, *, day: date) -> Any:
    return await client._get(f"{BASE}/availability", token=token, params={"date": day.isoformat()})


async def create(client: ApiClient, token: str, *, pet_id: int, starts_at: datetime) -> Any:
    return await client._post(
        BASE, token=token, json={"petId": pet_id, "startsAt": starts_at.isoformat()}
    )


async def list_mine(
    client: ApiClient,
    token: str,
    *,
    status: str | None,
    from_: datetime | None,
    to: datetime | None,
    page: int,
    size: int,
) -> Any:
    return await client._get(
        f"{BASE}/me",
        token=token,
        params={
            "status": status,
            "from": from_.isoformat() if from_ else None,
            "to": to.isoformat() if to else None,
            "page": page,
            "size": size,
        },
    )


async def get(client: ApiClient, token: str, appointment_id: int) -> Any:
    return await client._get(f"{BASE}/{appointment_id}", token=token)


async def update(
    client: ApiClient, token: str, appointment_id: int, *, pet_id: int, starts_at: datetime
) -> Any:
    return await client._put(
        f"{BASE}/{appointment_id}",
        token=token,
        json={"petId": pet_id, "startsAt": starts_at.isoformat()},
    )


async def delete(client: ApiClient, token: str, appointment_id: int) -> None:
    await client._delete(f"{BASE}/{appointment_id}", token=token)
