"""T040: pets + accommodation tools call only their documented API operations."""

import re

import httpx
import pytest

from tests.conftest import API, api_calls, call, future

pytestmark = pytest.mark.anyio
ALLOWED = [
    ("GET", r"/v1/pets"),
    ("GET", r"/v1/accommodation-bookings/free-dates"),
    ("GET", r"/v1/accommodation-bookings/availability"),
    ("POST", r"/v1/accommodation-bookings"),
    ("GET", r"/v1/accommodation-bookings/me"),
    ("GET", r"/v1/accommodation-bookings/\d+"),
    ("PUT", r"/v1/accommodation-bookings/\d+"),
    ("DELETE", r"/v1/accommodation-bookings/\d+"),
]


async def test_only_documented_operations(app, bearer, respx_mock):
    page = {"items": [], "page": {"number": 0, "size": 20, "totalItems": 0, "totalPages": 0}}
    respx_mock.route(host="api.test").mock(
        side_effect=lambda req: httpx.Response(204) if req.method == "DELETE" else httpx.Response(200, json=page)
    )
    args = {"pet_ids": [1], "check_in": future(5), "check_out": future(7)}
    for tool, a in [
        ("list_my_pets", {}),
        ("get_accommodation_free_dates", {}),
        ("get_accommodation_availability", {"from": future(1), "to": future(3)}),
        ("create_accommodation_booking", args),
        ("list_my_accommodation_bookings", {}),
        ("get_accommodation_booking", {"booking_id": 1}),
        ("update_accommodation_booking", {**args, "booking_id": 1}),
        ("cancel_accommodation_booking", {"booking_id": 1}),
    ]:
        await call(app, tool, a, bearer=bearer)
    calls = api_calls(respx_mock)
    assert len(calls) == 8
    for method, path in calls:
        assert any(m == method and re.fullmatch(p, path) for m, p in ALLOWED), (method, path)
