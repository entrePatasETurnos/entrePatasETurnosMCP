# Contract: MCP Tools

Input and output types are defined in [data-model.md](../data-model.md), sections 3 and 4. Errors
use the payload in section 5.

**Kind**:
- **R**: read-only; `readOnlyHint=true`; runs without confirmation.
- **W**: write; requires confirmation (see "Confirmation" below).
- **W!**: write that cancels something; also sets `destructiveHint=true`.

## Endpoint `/public/mcp` (no authentication)

| Tool | Kind | Input | API operation | Output |
|---|---|---|---|---|
| `register_account` | W | `RegisterAccountInput` | `POST /v1/users` (no Authorization header) | `RegistrationResult` |

**Errors returned as-is**:
- `400` with field errors becomes `invalid_request` plus `fields`;
- `409 USER_ALREADY_EXISTS`;
- `409 CPF_ALREADY_EXISTS`.

## Endpoint `/mcp` (OAuth 2.1 bearer required)

Each tool acts as the signed-in user, with `Authorization: Bearer <API access token>` added on the
server side.

| Tool | Kind | Input | API operation | Output |
|---|---|---|---|---|
| `list_my_pets` | R | `ListPetsInput` | `GET /v1/pets?page&size` | `PetPage` |
| `get_accommodation_free_dates` | R | `FreeDatesInput` | `GET /v1/accommodation-bookings/free-dates?from&to&pets&nights` | `FreeDates` |
| `get_accommodation_availability` | R | `AvailabilityInput` | `GET /v1/accommodation-bookings/availability?from&to` | `Availability` |
| `create_accommodation_booking` | W | `BookingInput` | `POST /v1/accommodation-bookings` `{petIds, checkIn, checkOut}` | `Booking` |
| `list_my_accommodation_bookings` | R | `BookingListInput` | `GET /v1/accommodation-bookings/me?status&from&to&page&size` | `BookingPage` |
| `get_accommodation_booking` | R | `BookingRefInput` | `GET /v1/accommodation-bookings/{id}` | `Booking` |
| `update_accommodation_booking` | W | `BookingInput` + `booking_id` | `PUT /v1/accommodation-bookings/{id}` | `Booking` |
| `cancel_accommodation_booking` | W! | `BookingRefInput` | `DELETE /v1/accommodation-bookings/{id}` (returns 204) | `CancelResult` |
| `get_bath_slots` | R | `BathSlotsInput` | `GET /v1/bath-appointments/availability?date` | `BathDay` |
| `create_bath_appointment` | W | `AppointmentInput` | `POST /v1/bath-appointments` `{petId, startsAt}` | `BathAppointment` |
| `list_my_bath_appointments` | R | `AppointmentListInput` | `GET /v1/bath-appointments/me?...` | `AppointmentPage` |
| `get_bath_appointment` | R | `AppointmentRefInput` | `GET /v1/bath-appointments/{id}` | `BathAppointment` |
| `update_bath_appointment` | W | `AppointmentInput` + `appointment_id` | `PUT /v1/bath-appointments/{id}` | `BathAppointment` |
| `cancel_bath_appointment` | W! | `AppointmentRefInput` | `DELETE /v1/bath-appointments/{id}` (returns 204) | `CancelResult` |
| `sign_out` | W | none | `DELETE /v1/auth/sessions/{apiSessionId}` | `{signed_out: true}` |

**Documented API errors that each tool passes through**:

- **Bookings**:
  - `400 invalid_request` + `fields`, including "pets not found" for pets the user doesn't own;
  - `409 pet_already_booked` + `details.pet_ids`;
  - `409 insufficient_capacity`;
  - `409 invalid_status_transition`;
  - `404 booking_not_found`;
  - `403 forbidden`;
  - `503 capacity_not_configured`.
- **Bath appointments**:
  - `400 invalid_request` + `fields`;
  - `409 pet_already_scheduled` + `details.pet_id`;
  - `409 insufficient_capacity`;
  - `409 invalid_status_transition`;
  - `404 appointment_not_found`;
  - `403 forbidden`;
  - `503`.
- **All tools**:
  - `401` from the API → one refresh attempt; if that fails, `sign_in_required`.
  - Timeout → `upstream_timeout` for R tools, `outcome_unknown` for W tools.

## Confirmation (Principle IV, research R8)

- **When the client supports elicitation**: a W tool calls `elicit` with a summary of the details.
  - For bookings: pet names, check-in, check-out and nights.
  - For bath appointments: pet name and slot time.
  - For registration: name, email and a masked CPF such as `***.***.**9-01`. The password is never
    shown.

  If the user declines, cancels or does not accept, the result is `cancelled_by_user` and the API
  is not called.
- **When the client lacks elicitation**: the input must contain `user_confirmed: true`.
  - Without it, the result is `confirmation_required`, and the payload lists the details the
    assistant must show the user.
  - The API is not called.

## Not exposed (FR-002, FR-003)

The server exposes none of these:
- approve, deny or complete for bookings or appointments;
- user administration and role changes;
- pet search across owners;
- pet create, edit or delete, and pet photos;
- push devices;
- email verification;
- any pet-training tool;
- any generic HTTP or passthrough tool.
