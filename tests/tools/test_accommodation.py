"""T039: accommodation tools - valid input, invalid input, API errors, authorization, confirmation."""

import json

import httpx
import pytest

from tests.conftest import API, Recorder, api_calls, call, future, last_json

pytestmark = pytest.mark.anyio
BASE = f"{API}/v1/accommodation-bookings"
BOOKING = {
    "id": 77, "ownerId": 42, "ownerName": "Owner", "status": "registered",
    "checkIn": "2026-12-01T14:00:00-03:00", "checkOut": "2026-12-04T12:00:00-03:00", "nights": 3,
    "pets": [{"id": 3, "name": "Rex"}], "review": None, "completion": None,
    "createdAt": "x", "updatedAt": "y", "_links": {"self": {"href": "/v1/accommodation-bookings/77"}},
}
VIEW = {"id": 77, "status": "registered", "check_in": "2026-12-01T14:00:00-03:00",
        "check_out": "2026-12-04T12:00:00-03:00", "nights": 3, "pets": [{"id": 3, "name": "Rex"}]}


def booking_args(**over):
    args = {"pet_ids": [3], "check_in": future(10, 14), "check_out": future(13, 12)}
    args.update(over)
    return args


# ------------------------------------------------------------------------------ valid


async def test_free_dates(app, bearer, respx_mock):
    route = respx_mock.get(f"{BASE}/free-dates").mock(return_value=httpx.Response(200, json={
        "from": "2026-12-01", "to": "2026-12-30", "capacity": 10, "pets": 2, "nights": 3,
        "firstFit": "2026-12-02", "days": [{"date": "2026-12-01", "free": 1, "requested": 2, "fits": False}],
        "_links": {}}))
    out = await call(app, "get_accommodation_free_dates", {"pets": 2, "nights": 3}, bearer=bearer)
    assert dict(route.calls.last.request.url.params) == {"pets": "2", "nights": "3"}
    assert out == {"from": "2026-12-01", "to": "2026-12-30", "pets": 2, "nights": 3,
                   "first_fit": "2026-12-02", "days": [{"date": "2026-12-01", "free": 1, "fits": False}]}


async def test_availability_keeps_offsets(app, bearer, respx_mock):
    route = respx_mock.get(f"{BASE}/availability").mock(return_value=httpx.Response(200, json={
        "from": "a", "to": "b", "capacity": 10, "intervals": [{"start": "a", "end": "b", "available": 4}], "_links": {}}))
    out = await call(app, "get_accommodation_availability",
                     {"from": "2026-12-01T00:00:00-03:00", "to": "2026-12-10T00:00:00-03:00"}, bearer=bearer)
    assert dict(route.calls.last.request.url.params) == {
        "from": "2026-12-01T00:00:00-03:00", "to": "2026-12-10T00:00:00-03:00"}
    assert out["intervals"] == [{"start": "a", "end": "b", "available": 4}]


async def test_create_sends_documented_body_after_confirmation(app, bearer, respx_mock):
    route = respx_mock.post(BASE).mock(return_value=httpx.Response(201, json=BOOKING))
    rec = Recorder()
    args = booking_args()
    out = await call(app, "create_accommodation_booking", args, bearer=bearer, recorder=rec)
    assert out == VIEW
    assert last_json(route) == {"petIds": [3], "checkIn": args["check_in"], "checkOut": args["check_out"]}
    assert route.calls.last.request.headers["Authorization"] == "Bearer api-at-1"
    assert len(rec.prompts) == 1 and args["check_in"] in rec.prompts[0]


async def test_list_get_update_cancel(app, bearer, respx_mock):
    lst = respx_mock.get(f"{BASE}/me").mock(return_value=httpx.Response(200, json={
        "items": [BOOKING], "page": {"number": 0, "size": 20, "totalItems": 1, "totalPages": 1}, "_links": {}}))
    out = await call(app, "list_my_accommodation_bookings", {"status": "registered"}, bearer=bearer)
    assert out["items"] == [VIEW] and dict(lst.calls.last.request.url.params) == {"status": "registered", "page": "0", "size": "20"}

    respx_mock.get(f"{BASE}/77").mock(return_value=httpx.Response(200, json=BOOKING))
    assert await call(app, "get_accommodation_booking", {"booking_id": 77}, bearer=bearer) == VIEW

    put = respx_mock.put(f"{BASE}/77").mock(return_value=httpx.Response(200, json=BOOKING))
    assert await call(app, "update_accommodation_booking", booking_args(booking_id=77), bearer=bearer) == VIEW
    assert set(last_json(put)) == {"petIds", "checkIn", "checkOut"}

    respx_mock.delete(f"{BASE}/77").mock(return_value=httpx.Response(204))
    assert await call(app, "cancel_accommodation_booking", {"booking_id": 77}, bearer=bearer) == {
        "cancelled": True, "booking_id": 77}


async def test_denied_booking_shows_reason(app, bearer, respx_mock):
    denied = {**BOOKING, "status": "denied", "review": {"reviewerId": 1, "reviewedAt": "x", "denialReason": "lotado"}}
    respx_mock.get(f"{BASE}/77").mock(return_value=httpx.Response(200, json=denied))
    out = await call(app, "get_accommodation_booking", {"booking_id": 77}, bearer=bearer)
    assert out["denial_reason"] == "lotado" and "reviewerId" not in json.dumps(out)


# ---------------------------------------------------------------------------- invalid


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_accommodation_booking", {"check_in": "2026-12-01T14:00:00"}),  # naive
        ("create_accommodation_booking", {"check_out": future(5)}),  # before check-in
        ("create_accommodation_booking", {"check_in": "2020-01-01T14:00:00-03:00", "check_out": "2020-01-03T14:00:00-03:00"}),
        ("create_accommodation_booking", {"pet_ids": []}),
        ("create_accommodation_booking", {"pet_ids": list(range(1, 52))}),
        ("create_accommodation_booking", {"pet_ids": [3, 3]}),
        ("create_accommodation_booking", {"pet_ids": [0]}),
        ("create_accommodation_booking", {"owner_id": 1}),
        ("create_accommodation_booking", {"user_id": 1}),
        ("get_accommodation_free_dates", {"nights": 91}),
        ("get_accommodation_free_dates", {"pets": 51}),
        ("get_accommodation_free_dates", {"from_date": "2020-01-01"}),
        ("get_accommodation_free_dates", {"from_date": future(1)[:10], "to_date": future(400)[:10]}),
        ("get_accommodation_availability", {"from": "2026-12-10T00:00:00-03:00", "to": "2026-12-01T00:00:00-03:00"}),
        ("list_my_accommodation_bookings", {"status": "pending"}),
        ("get_accommodation_booking", {"booking_id": 0}),
    ],
)
async def test_invalid_input_never_calls_api(app, bearer, respx_mock, tool, args):
    if tool in ("create_accommodation_booking",):
        args = booking_args(**args)
    out = await call(app, tool, args, bearer=bearer)
    assert out["error_code"] == "validation_error" and out["fields"]
    assert api_calls(respx_mock) == []


# ------------------------------------------------------------------------- API errors


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (400, {"error": "invalid_request", "message": "campos inválidos", "fields": {"petIds": "pets não encontrados"}},
         {"error_code": "invalid_request", "fields": {"petIds": "pets não encontrados"}}),
        (409, {"error": "pet_already_booked", "message": "já reservado", "petIds": [3]},
         {"error_code": "pet_already_booked", "details": {"pet_ids": [3]}}),
        (409, {"error": "insufficient_capacity", "message": "sem vagas"}, {"error_code": "insufficient_capacity"}),
        (503, {"error": "capacity_not_configured", "message": "m"}, {"error_code": "capacity_not_configured"}),
    ],
)
async def test_create_api_errors_passed_through(app, bearer, respx_mock, status, body, expected):
    respx_mock.post(BASE).mock(return_value=httpx.Response(status, json=body))
    out = await call(app, "create_accommodation_booking", booking_args(), bearer=bearer)
    assert out["is_error"] and out["http_status"] == status
    for key, value in expected.items():
        assert out[key] == value


@pytest.mark.parametrize(
    ("status", "code"), [(409, "invalid_status_transition"), (404, "booking_not_found"), (403, "forbidden")]
)
async def test_cancel_api_errors(app, bearer, respx_mock, status, code):
    respx_mock.delete(f"{BASE}/77").mock(return_value=httpx.Response(status, json={"error": code, "message": "m"}))
    out = await call(app, "cancel_accommodation_booking", {"booking_id": 77}, bearer=bearer)
    assert out["error_code"] == code and "cancelled" not in out


async def test_write_timeout_is_outcome_unknown(app, bearer, respx_mock):
    respx_mock.post(BASE).mock(side_effect=httpx.ReadTimeout("slow"))
    out = await call(app, "create_accommodation_booking", booking_args(), bearer=bearer)
    assert out["error_code"] == "outcome_unknown"


# ---------------------------------------------------------------------- confirmation


@pytest.mark.parametrize("answer", ["decline", "cancel", "reject"])
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_accommodation_booking", None),
        ("update_accommodation_booking", {"booking_id": 77}),
        ("cancel_accommodation_booking", {"booking_id": 77}),
    ],
)
async def test_refused_confirmation_never_calls_api(app, bearer, respx_mock, answer, tool, args):
    payload = args if tool == "cancel_accommodation_booking" else booking_args(**(args or {}))
    out = await call(app, tool, payload, bearer=bearer, elicitation=answer)
    assert out["is_error"]
    assert api_calls(respx_mock) == []


async def test_without_elicitation_requires_user_confirmed(app, bearer, respx_mock):
    route = respx_mock.post(BASE).mock(return_value=httpx.Response(201, json=BOOKING))
    out = await call(app, "create_accommodation_booking", booking_args(), bearer=bearer, elicitation=None)
    assert out["error_code"] == "confirmation_required"
    assert "check-in" in out["details"]["summary"]
    assert not route.called
    out = await call(app, "create_accommodation_booking", booking_args(user_confirmed=True), bearer=bearer, elicitation=None)
    assert out == VIEW and route.call_count == 1


async def test_legacy_protocol_client_uses_fallback(app, bearer, respx_mock):
    route = respx_mock.post(BASE).mock(return_value=httpx.Response(201, json=BOOKING))
    out = await call(app, "create_accommodation_booking", booking_args(), bearer=bearer, mode="legacy")
    assert out["error_code"] == "confirmation_required" and not route.called


# ---------------------------------------------------------------------- authorization


async def test_foreign_pet_rejected_by_api_is_reported(app, bearer, respx_mock):
    respx_mock.post(BASE).mock(return_value=httpx.Response(400, json={
        "error": "invalid_request", "message": "m", "fields": {"petIds": "pets não encontrados"}}))
    out = await call(app, "create_accommodation_booking", booking_args(pet_ids=[999]), bearer=bearer)
    assert out["error_code"] == "invalid_request" and "petIds" in out["fields"]
