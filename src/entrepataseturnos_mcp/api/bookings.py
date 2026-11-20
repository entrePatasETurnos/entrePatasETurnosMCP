"""Accommodation bookings: ``/v1/accommodation-bookings`` (API specs 030, 034, 037)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .client import ApiClient

BASE = "/v1/accommodation-bookings"


async def free_dates(
    client: ApiClient,
    token: str,
    *,
    from_date: date | None,
    to_date: date | None,
    pets: int,
    nights: int,
) -> Any:
    return await client._get(
        f"{BASE}/free-dates",
        token=token,
        params={
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None,
            "pets": pets,
            "nights": nights,
        },
    )


async def availability(client: ApiClient, token: str, *, from_: datetime, to: datetime) -> Any:
    return await client._get(
        f"{BASE}/availability",
        token=token,
        params={"from": from_.isoformat(), "to": to.isoformat()},
    )


def _body(pet_ids: list[int], check_in: datetime, check_out: datetime) -> dict[str, Any]:
    return {"petIds": pet_ids, "checkIn": check_in.isoformat(), "checkOut": check_out.isoformat()}


async def create(
    client: ApiClient, token: str, *, pet_ids: list[int], check_in: datetime, check_out: datetime
) -> Any:
    return await client._post(BASE, token=token, json=_body(pet_ids, check_in, check_out))


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


async def get(client: ApiClient, token: str, booking_id: int) -> Any:
    return await client._get(f"{BASE}/{booking_id}", token=token)


async def update(
    client: ApiClient,
    token: str,
    booking_id: int,
    *,
    pet_ids: list[int],
    check_in: datetime,
    check_out: datetime,
) -> Any:
    return await client._put(
        f"{BASE}/{booking_id}", token=token, json=_body(pet_ids, check_in, check_out)
    )


async def delete(client: ApiClient, token: str, booking_id: int) -> None:
    await client._delete(f"{BASE}/{booking_id}", token=token)
