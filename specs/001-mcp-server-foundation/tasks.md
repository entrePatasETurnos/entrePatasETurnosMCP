---

description: "Task list for the EntrePatasETurnos MCP Server Foundation"
---

# Tasks: EntrePatasETurnos MCP Server Foundation

**Input**: Design documents from `/specs/001-mcp-server-foundation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md,
contracts/http-endpoints.md, quickstart.md

**Tests**: REQUIRED. Spec FR-024 and constitution Principle VIII require tests for every tool:
valid input, invalid input, API errors, and authorization boundaries. These tests must show that the
documented API operation is called and that failures are never reported as success. Write each
story's tests first and confirm they fail before implementing.

**Organization**: Tasks are grouped by user story. Story phases are ordered by dependency first and
then by priority. User Story 5 (sign-in, P1) comes before User Story 1, because every authenticated
tool needs it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1–US6)

## Path Conventions

- The package is `src/entrepataseturnos_mcp/`; the tests are in `tests/`; manifests are in
  `deploy/k8s/`. All paths are relative to the repository root.
- **Model placement**: shared types go in `src/entrepataseturnos_mcp/tools/models.py`. Each domain's
  input and output models live in its own tool module, so stories never edit the same model file.
- **Tool registration**: every tool is registered in `src/entrepataseturnos_mcp/servers.py`. Those
  registration tasks are sequential, never [P].
- **References**: "DM §n" means data-model.md section n. "R n" means research.md decision n.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the uv project, its tooling and its skeleton.

- [ ] T001 Initialize the uv package project at the repository root by running `uv init --package --name entrepataseturnos-mcp --python 3.13`.
  - Resulting files: `pyproject.toml`, `.python-version` (3.13) and `src/entrepataseturnos_mcp/__init__.py`.
  - Set `[project.scripts] entrepataseturnos-mcp = "entrepataseturnos_mcp.__main__:main"`.
- [ ] T002 Add the runtime dependencies to `pyproject.toml`: `uv add "mcp>=2.3,<3" "httpx>=0.28" "pydantic>=2.12" "pydantic-settings>=2.16" "redis>=8.1" "cryptography>=50" "uvicorn>=0.54"`.
  - Then add the dev dependencies: `uv add --dev "pytest>=9" "respx>=0.23" "fakeredis>=2.40" ruff mypy`.
  - Commit the generated `uv.lock`.
- [ ] T003 [P] Configure the tools in `pyproject.toml`.
  - `[tool.ruff]`: line-length 100, target py313; lint rules `E,F,I,B,UP,S,ASYNC`.
  - `[tool.mypy]`: strict, `files = ["src"]`.
  - `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, the anyio marker, `-ra`.
- [ ] T004 [P] Create `.gitignore` (`.venv/`, `.env`, `.env.*` except `!.env.example`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`).
  - Create `.dockerignore`, which also excludes `tests/`, `specs/`, `.specify/`, `.claude/` and `deploy/`.
  - Create `.env.example`. It lists every `MCP_*` variable from DM §1. Non-secret variables get sample values. Secret variables are left empty.
- [ ] T005 [P] Create a `Makefile` with these targets (`TAG ?= latest`, `IMAGE := entrepataseturnos/entrepataseturnos-mcp-server`):
  - `sync` (`uv sync`)
  - `lint` (`uv run ruff check . && uv run ruff format --check . && uv run mypy`)
  - `test` (`uv run pytest`)
  - `run` (`uv run entrepataseturnos-mcp`)
  - `image` (`docker build -t $(IMAGE):$(TAG) .`)
  - `docker-run` (`docker run --rm --env-file .env -p 8000:8000 $(IMAGE):$(TAG)`)
  - `deploy` (`kubectl apply -k deploy/k8s`)
- [ ] T006 [P] Create empty package modules `src/entrepataseturnos_mcp/api/__init__.py`, `src/entrepataseturnos_mcp/auth/__init__.py` and `src/entrepataseturnos_mcp/tools/__init__.py`.
  - Also create empty `__init__.py` files in `tests/unit/`, `tests/auth/`, `tests/tools/`, `tests/contract/` and `tests/integration/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, logging, the API client core, error mapping, shared validation types,
confirmation, crypto, Redis storage, app composition and test fixtures.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundational

- [ ] T007 [P] Write `tests/unit/test_config.py`.
  - Loading succeeds with every required `MCP_*` variable set.
  - Each missing required variable makes loading fail with a message that names the variable.
  - `repr(settings)` and the error output never contain the values of `MCP_GOOGLE_CLIENT_SECRET`, `MCP_REDIS_URL` or `MCP_TOKEN_ENCRYPTION_KEY`.
  - `MCP_PUBLIC_BASE_URL` must use https, except for `http://localhost`.
  - `MCP_TOKEN_ENCRYPTION_KEY` must decode to 32 bytes.
- [ ] T008 [P] Write `tests/unit/test_logging.py`. The JSON formatter must replace these keys with `"[REDACTED]"`, case-insensitively, including in nested dicts and in `extra=`:
  - `authorization`, `password`, `cpf`, `idToken`, `code`, `secret`, and any key containing `token`.
- [ ] T009 [P] Write `tests/unit/test_api_client.py`, using respx.
  - Every request goes to `MCP_API_BASE_URL` with an `X-Correlation-Id` header.
  - A bearer token is attached only when one is passed in.
  - A GET is retried exactly once on `httpx.ConnectError`. A POST, PUT or DELETE is never retried.
  - A read timeout raises `UpstreamTimeout` for a GET, and `OutcomeUnknown` for a write.
  - A 4xx/5xx JSON `{error, message}` raises `ApiError(code, message, status)`.
  - `{fields}` and extra keys such as `petIds` and `petId` are kept on the error.
  - A non-JSON error body raises `ApiError("upstream_unavailable")` for 5xx, and `upstream_invalid_response` otherwise.
  - A 2xx with malformed JSON raises `upstream_invalid_response`.
- [ ] T010 [P] Write `tests/unit/test_tool_errors.py`. `to_tool_error()` produces the DM §5 payload: `error_code`, `message` and `http_status`, plus `fields` and `details` only when they are non-empty. The `petIds` and `petId` extras are mapped to `details.pet_ids` and `details.pet_id`.
- [ ] T011 [P] Write `tests/unit/test_models_common.py`.
  - `OffsetDateTime` accepts `2026-12-01T14:00:00-03:00` and rejects `2026-12-01T14:00:00`.
  - `LocalDate` accepts only `YYYY-MM-DD`.
  - `PositiveId` rejects 0.
  - `Page` rejects `size` 0 or 101 and `page` -1.
  - `StrictInput` (`extra="forbid"`) rejects `user_id`, `owner_id`, `account_id` and `role`.
- [ ] T012 [P] Write `tests/unit/test_confirm.py`.
  - With an elicitation-capable context: an accepted `confirm=true` lets the call proceed; decline, cancel or `confirm=false` raises a `cancelled_by_user` `ToolError`.
  - Without elicitation support: `user_confirmed=True` proceeds; missing or false raises `confirmation_required`, and the payload's `details.summary` lists the fields shown to the user.
- [ ] T013 [P] Write `tests/unit/test_crypto.py`.
  - Encrypting and then decrypting with AES-GCM returns the original value.
  - Tampered ciphertext fails.
  - Two encryptions of the same value differ (random nonce).
  - `hash_token()` returns the hex SHA-256, and the result does not contain the token itself.
- [ ] T014 [P] Write `tests/unit/test_store.py`, using fakeredis.
  - Each repository from DM §2 saves, loads and deletes its records under the `epet:mcp:` prefix with the documented TTLs.
  - `consume_pending()` and `consume_code()` are single-use: a second call returns None.
  - The token index set collects every token hash for a session, and `delete_session_cascade()` removes them all.

### Implementation for Foundational

- [ ] T015 [P] Implement `Settings` in `src/entrepataseturnos_mcp/config.py`, following DM §1.
  - Use pydantic-settings with `env_prefix="MCP_"` and `SecretStr` for secrets.
  - Validate the https rule and the 32-byte key.
  - Add `load_settings()`. On failure it writes `missing/invalid setting: MCP_X` lines to stderr, with no values, and calls `SystemExit(2)`.
- [ ] T016 [P] Implement the JSON log formatter and the recursive redaction filter in `src/entrepataseturnos_mcp/logging.py`.
  - `configure_logging(level)` installs them on the root logger.
  - It also sets the uvicorn access log to omit query strings, because OAuth `code` and `state` appear there.
- [ ] T017 [P] Implement the exceptions in `src/entrepataseturnos_mcp/api/errors.py`: `ApiError(code, message, status, fields, extras)`, `UpstreamTimeout`, `OutcomeUnknown` and `UpstreamUnavailable`.
- [ ] T018 Implement `ApiClient` in `src/entrepataseturnos_mcp/api/client.py` (depends on T015 and T017).
  - It wraps a single `httpx.AsyncClient` with `base_url`, `Timeout(connect=3, read=settings.api_timeout_seconds, write=10, pool=5)` and `Limits(max_connections=20)`.
  - It has private `_get`, `_post`, `_put` and `_delete` methods that take a path, a bearer token, JSON or params, and a `write` flag. These enforce the retry and timeout rules from R5 and the error mapping from T009.
  - Paths must start with `/v1/`; anything else is an assertion error.
  - There is **no** public generic request method (FR-002).
  - It logs the method, the path template, the status and the duration, and never logs bodies.
- [ ] T019 [P] Implement `to_tool_error(exc) -> ToolError` in `src/entrepataseturnos_mcp/tools/errors.py`. It handles `ApiError`, `UpstreamTimeout`, `OutcomeUnknown`, `UpstreamUnavailable` and pydantic `ValidationError` (which becomes `validation_error` with `fields`), following DM §5. It returns a JSON string payload.
- [ ] T020 [P] Implement the shared types in `src/entrepataseturnos_mcp/tools/models.py`.
  - The types are `StrictInput` (base model with `extra="forbid"`), `OffsetDateTime` (an aware `datetime` validator that rejects naive values), `LocalDate`, `PositiveId`, `Page` (page ≥ 0, size 1–100) and `PageInfo` (output).
  - Add the helper `not_in_past(dt)`.
- [ ] T021 [P] Implement `require_confirmation(ctx, summary: dict, user_confirmed: bool | None)` in `src/entrepataseturnos_mcp/tools/confirm.py`, following R8.
  - Use `ctx.elicit()` with a `confirm: bool` schema when the client's capabilities include elicitation.
  - Otherwise use the `user_confirmed` fallback.
  - Raise a `ToolError` with `cancelled_by_user` or `confirmation_required`.
- [ ] T022 [P] Implement `encrypt`, `decrypt` and `hash_token` (AES-256-GCM with a 12-byte random nonce, key from settings) in `src/entrepataseturnos_mcp/auth/crypto.py`.
- [ ] T023 Implement the async Redis repositories in `src/entrepataseturnos_mcp/auth/store.py`, following DM §2 (depends on T022).
  - The repositories are `SessionRepo` (with encrypted token fields), `ClientRepo`, `PendingRepo`, `CodeRepo`, `AccessTokenRepo`, `RefreshTokenRepo` and the token index.
  - Add `acquire_refresh_lock`, `release_refresh_lock` and `delete_session_cascade`.
  - A Redis connection error raises `SessionStoreUnavailable`.
- [ ] T024 Implement the app skeleton in `src/entrepataseturnos_mcp/servers.py` and `src/entrepataseturnos_mcp/app.py`.
  - `servers.py`: `build_authenticated_server(provider, settings)` and `build_public_server()` return `MCPServer` instances. Tools are registered later by the story tasks.
  - `app.py`: `create_app(settings)` builds one Starlette app.
    - Mount the authenticated server's `streamable_http_app(stateless_http=True, json_response=True)` at `/mcp`, and the public one at `/public/mcp`.
    - Its lifespan opens the `ApiClient` and the Redis client, and runs both session managers.
    - Shared resources are available to tools through the lifespan context.
- [ ] T025 Implement `main()` in `src/entrepataseturnos_mcp/__main__.py`: `load_settings()`, then `configure_logging()`, then `uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=True)`.
- [ ] T026 Create the shared fixtures in `tests/conftest.py`.
  - `settings` (test values; the API URL is `http://api.test`) and `respx_api`, a respx router scoped to the API base URL.
  - `redis` (fakeredis async) and `app` (from `create_app`, with fakeredis injected).
  - `signed_in_session`: seeds a `SessionRepo` record (user 42, valid API token `api-at-1`) and an MCP access token. It returns the bearer value.
  - `mcp_client(endpoint, bearer=None, elicitation="accept"|"decline"|None)`: an in-process MCP client connected to the Starlette app through `httpx.ASGITransport`.

**Checkpoint**: The foundation is ready, and `uv run pytest tests/unit` passes.

---

## Phase 3: User Story 5 - Sign in to use the assistant (Priority: P1)

**Goal**: The MCP server is the OAuth 2.1 authorization server for its clients and federates sign-in
to Google. It holds the API session server-side and encrypted, refreshes it, and supports sign-out.

**Independent Test**: Connect an OAuth-capable MCP client to `/mcp` and complete Google sign-in with
a test account. A read-only call then reaches the API as that user. No token is visible to the
client except the opaque MCP token. See quickstart §3, steps 1–2, 9 and 10.

### Tests for User Story 5 ⚠️

- [ ] T027 [P] [US5] Write `tests/auth/test_provider.py`.
  - Dynamic client registration stores the client.
  - `authorize()` stores a pending authorization (with a 600 s TTL) and returns a Google authorize URL that carries `client_id=MCP_GOOGLE_CLIENT_ID`, the redirect `{MCP_PUBLIC_BASE_URL}/oauth/google/callback`, `scope=openid email profile`, `code_challenge_method=S256` and `state`.
  - `exchange_authorization_code()` issues opaque access and refresh tokens and stores only their hashes. A reused code fails.
  - `load_access_token()` resolves the session.
  - `exchange_refresh_token()` rotates the refresh token.
  - `revoke_token()` calls `DELETE /v1/auth/sessions/{id}` and cascades the deletion.
- [ ] T028 [P] [US5] Write `tests/auth/test_google_callback.py`, using respx for the Google token endpoint and the API.
  - **Success**: exactly one call to `POST /v1/auth/sessions/google` with body `{idToken, deviceName:"EntrePatasETurnos MCP"}`, a stored session record whose tokens are encrypted, and a 302 to the client's `redirect_uri` with `code` and the client's `state`.
  - **API errors**: 409 `account_link_required`, 403 `account_unavailable`, 401 `invalid_assertion` and 503 `provider_unavailable` each produce a 302 to the client with `error` and an `error_description` that contains the API code. No session is stored.
  - **Unknown or expired state** produces a 400.
  - **Google token exchange failure** produces a 302 with `error=server_error`.
- [ ] T029 [P] [US5] Write `tests/auth/test_session_refresh.py`.
  - `api_token()` returns the stored token when it expires more than 60 s from now, and makes no API call.
  - When it expires within 60 s: one call to `POST /v1/auth/sessions/{id}/refresh {refreshToken}`, and the rotated tokens are stored encrypted.
  - Two concurrent calls produce exactly one refresh call (lock).
  - A 409 `refresh_in_progress` is retried once.
  - A 401 `invalid_refresh_token` deletes the session cascade and raises `sign_in_required`.
  - An unavailable Redis raises `session_store_unavailable`.
- [ ] T030 [P] [US5] Write `tests/integration/test_mcp_auth.py`.
  - `POST /mcp` without a bearer, or with an unknown one, returns 401 with a `WWW-Authenticate` header that references the protected-resource metadata.
  - `/.well-known/oauth-authorization-server` advertises `/authorize`, `/token`, `/register` and `/revoke` under the issuer.
  - The `sign_out` tool calls `DELETE /v1/auth/sessions/{id}`, returns `{signed_out:true}`, and the next call with the same bearer returns 401.
  - Two `create_app()` instances that share one fakeredis both accept the same bearer.
  - No tool result or log record contains `api-at-1` or a refresh token value.

### Implementation for User Story 5

- [ ] T031 [P] [US5] Implement the session API calls in `src/entrepataseturnos_mcp/api/auth.py`: `create_google_session(id_token)` (`POST /v1/auth/sessions/google`), `refresh_session(session_id, refresh_token)` (`POST /v1/auth/sessions/{id}/refresh`) and `delete_session(session_id, access_token)` (`DELETE /v1/auth/sessions/{id}`). Each returns a typed `SessionTokens` model.
- [ ] T032 [P] [US5] Implement the Google helpers in `src/entrepataseturnos_mcp/auth/google.py`.
  - `build_authorize_url(state, code_challenge)` uses `https://accounts.google.com/o/oauth2/v2/auth`.
  - `exchange_code(code, code_verifier)` calls `https://oauth2.googleapis.com/token` with the client id and secret through its own `httpx.AsyncClient` with a 10 s timeout, and returns the `id_token`.
  - Implement the PKCE pair generator.
- [ ] T033 [US5] Implement `SessionService` in `src/entrepataseturnos_mcp/auth/session.py` (depends on T023 and T031).
  - `api_token(sid)` implements the refresh, lock and retry rules from R3 step 7 and T029.
  - `sign_out(sid)` calls `delete_session` and then `delete_session_cascade`. It cascades even when the API call fails, and logs the failure.
  - Add the helper `current_session_id(ctx)`, which reads the session id from the SDK's `get_access_token()`. Tools must never take identity from their arguments.
- [ ] T034 [US5] Implement `RedisOAuthProvider(OAuthAuthorizationServerProvider)` in `src/entrepataseturnos_mcp/auth/provider.py`. It must implement these methods (depends on T023, T032 and T033):
  - `get_client`, `register_client` and `authorize`. `authorize` creates the pending authorization with the Google PKCE verifier and returns the Google URL.
  - `load_authorization_code` and `exchange_authorization_code`.
  - `load_refresh_token` and `exchange_refresh_token`.
  - `load_access_token` and `revoke_token`.
- [ ] T035 [US5] Implement the custom route `GET /oauth/google/callback` in `src/entrepataseturnos_mcp/auth/google.py`, following http-endpoints.md (depends on T034).
  - Consume the pending authorization, exchange the code with Google, and call `create_google_session`.
  - Store the session, issue the MCP code, and redirect to the client.
  - Map errors as tested in T028. Never log `code`, `state` or tokens.
- [ ] T036 [US5] Implement the `sign_out` tool in `src/entrepataseturnos_mcp/tools/account.py`.
  - It takes no inputs and has annotations `readOnlyHint=false`.
  - It calls `require_confirmation` with the summary "sign out of EntrePatasETurnos" and then `SessionService.sign_out`.
- [ ] T037 [US5] Wire the auth into `src/entrepataseturnos_mcp/servers.py` and `src/entrepataseturnos_mcp/app.py`.
  - Set `AuthSettings(issuer_url=MCP_PUBLIC_BASE_URL, resource_server_url={MCP_PUBLIC_BASE_URL}/mcp, client_registration_options=ClientRegistrationOptions(enabled=True), revocation_options=RevocationOptions(enabled=True))`.
  - Pass `auth_server_provider=RedisOAuthProvider(...)`.
  - Register the callback route and the `sign_out` tool.

**Checkpoint**: Sign-in, refresh and sign-out work. T027–T030 pass.

---

## Phase 4: User Story 1 - Book accommodation for my pets (Priority: P1) 🎯 MVP

**Goal**: A signed-in owner can list their pets, check free dates and availability, and create,
list, view, update and cancel their own accommodation bookings, with confirmation before every
write.

**Independent Test**: Using the `signed_in_session` fixture, or quickstart §3 steps 3–6: free dates
are returned, a confirmed booking is created through `POST /v1/accommodation-bookings`, a declined
booking is never sent, and the booking appears in `list_my_accommodation_bookings`.

### Tests for User Story 1 ⚠️

- [ ] T038 [P] [US1] Write `tests/tools/test_pets.py` for `list_my_pets`.
  - **Valid**: calls `GET /v1/pets?page=0&size=20` with `Authorization: Bearer api-at-1`, and returns `PetSummary` items without `_links`, `photos` or timestamps.
  - **Invalid**: `size=101` returns `validation_error`, and the API is not called.
  - **API errors**: 401 followed by a failed refresh returns `sign_in_required`; a 5xx returns `upstream_unavailable`; a timeout returns `upstream_timeout`.
  - **Authorization**: no bearer is rejected; a `user_id` argument is rejected.
- [ ] T039 [P] [US1] Write `tests/tools/test_accommodation.py`. Cover each of the seven accommodation tools from mcp-tools.md with the four required categories:
  - **Valid**: the exact method, path, query and body (`petIds`, `checkIn`, `checkOut` with offsets preserved) are sent, and the output is trimmed per DM §4.
  - **Invalid**: naive datetimes; `check_out ≤ check_in`; `check_in` in the past; 0 or 51 pets; duplicate pet ids; `nights` 91; a range longer than 366 days; an unknown `status`. In each case the API is not called.
  - **API errors**, each passed through with its code: `400 invalid_request` with `fields.petIds`; `409 pet_already_booked` with `details.pet_ids`; `409 insufficient_capacity`; `409 invalid_status_transition`; `404 booking_not_found`; `503 capacity_not_configured`. In none of these cases does the tool report success.
  - **Authorization**: no bearer; an `owner_id` argument is rejected; a foreign pet's 400 is passed through.
  - **Confirmation**: create, update and cancel with elicitation declined return `cancelled_by_user` with zero API calls. Without elicitation and without `user_confirmed`, they return `confirmation_required` with zero API calls.
  - **Write timeout**: returns `outcome_unknown`.
- [ ] T040 [P] [US1] Write `tests/contract/test_accommodation_contract.py`. Every API request made by the pets and accommodation tools must use one of these method and path pairs, and nothing else:
  - `GET /v1/pets`
  - `GET /v1/accommodation-bookings/free-dates`
  - `GET /v1/accommodation-bookings/availability`
  - `POST /v1/accommodation-bookings`
  - `GET /v1/accommodation-bookings/me`
  - `GET|PUT|DELETE /v1/accommodation-bookings/{id}`

### Implementation for User Story 1

- [ ] T041 [P] [US1] Implement `list_pets(token, page, size)` (`GET /v1/pets`) in `src/entrepataseturnos_mcp/api/pets.py`.
- [ ] T042 [P] [US1] Implement the booking API calls in `src/entrepataseturnos_mcp/api/bookings.py`:
  - `free_dates(token, from_date, to_date, pets, nights)`
  - `availability(token, from_, to)`
  - `create(token, pet_ids, check_in, check_out)`
  - `list_mine(token, status, from_, to, page, size)`
  - `get(token, booking_id)`
  - `update(token, booking_id, ...)`
  - `delete(token, booking_id)`

  Datetimes are serialized in ISO-8601 with their offset kept.
- [ ] T043 [US1] Implement `list_my_pets` in `src/entrepataseturnos_mcp/tools/pets.py` (depends on T033 and T041).
  - Define the `ListPetsInput` and `PetSummary` models there.
  - The description says the tool is read-only, with `readOnlyHint=true`.
- [ ] T044 [US1] Implement the seven accommodation tools in `src/entrepataseturnos_mcp/tools/accommodation.py`, following mcp-tools.md (depends on T020, T021, T033 and T042).
  - Define the domain models there: `FreeDatesInput`, `AvailabilityInput`, `BookingInput`, `BookingUpdateInput`, `BookingListInput`, `BookingRefInput`, `FreeDates`, `Availability`, `Booking` and `BookingPage`.
  - Validators follow DM §3.
  - Write tools call `require_confirmation` with a summary of pet names, check-in, check-out and nights before calling the API.
  - Descriptions state the write and confirmation rules.
  - Cancel has `destructiveHint=true`.
  - Errors go through `to_tool_error`.
- [ ] T045 [US1] Register `list_my_pets` and the seven accommodation tools on the authenticated server in `src/entrepataseturnos_mcp/servers.py`.

**Checkpoint**: The MVP works: sign-in plus accommodation booking. T038–T040 pass.

---

## Phase 5: User Story 6 - Deploy and operate the server in the cluster (Priority: P1)

**Goal**: The server provides health and readiness probes and fails fast on bad configuration. It
ships as a secret-free image named `entrepataseturnos/entrepataseturnos-mcp-server:latest`, with
kustomize manifests and a README.

**Independent Test**: Follow quickstart §2, §5 and §6. The image builds; probes behave as described;
the pods become Ready; an MCP client lists the tools through the Service.

### Tests for User Story 6 ⚠️

- [ ] T046 [P] [US6] Write `tests/integration/test_health.py`.
  - `/healthz` returns 200 `{"status":"ok"}` even when Redis and the API are down.
  - `/readyz` returns 200 when Redis answers PING and `GET /v1/info` returns 2xx.
  - It returns 503, naming the failing check, when Redis is down, when the API returns 5xx, or when the API times out after 2 s.
  - Results are cached for 5 s.
  - The response body contains no URLs that include credentials.
- [ ] T047 [P] [US6] Write `tests/unit/test_main.py`.
  - When `MCP_API_BASE_URL` is unset, `main()` exits with code 2.
  - stderr names the variable, and contains no secret values set in the environment.

### Implementation for User Story 6

- [ ] T048 [US6] Implement `src/entrepataseturnos_mcp/health.py`, following R10, and mount its routes in `src/entrepataseturnos_mcp/app.py`.
  - `/healthz` is a liveness handler.
  - `/readyz` runs the settings, Redis PING (1 s timeout) and `GET /v1/info` (2 s timeout) checks, cached for 5 s.
- [ ] T049 [P] [US6] Create the multi-stage `Dockerfile`, following R13.
  - **Builder**: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`. Copy `pyproject.toml` and `uv.lock`, run `uv sync --frozen --no-dev --no-install-project`, copy `src/`, then run `uv sync --frozen --no-dev --no-editable`.
  - **Runtime**: `python:3.13-slim-bookworm`. Copy `/app/.venv`, set `PATH=/app/.venv/bin:$PATH`, `USER 10001:10001`, `EXPOSE 8000` and `CMD ["entrepataseturnos-mcp"]`.
  - Do not use `ENV` or `ARG` for secrets.
- [ ] T050 [P] [US6] Create the Kubernetes base manifests:
  - `deploy/k8s/namespace.yaml`: namespace `entrepataseturnos`.
  - `deploy/k8s/configmap.yaml`: `entrepataseturnos-mcp-config`, with `MCP_API_BASE_URL`, `MCP_PUBLIC_BASE_URL`, `MCP_GOOGLE_CLIENT_ID`, `MCP_API_TIMEOUT_SECONDS` and `MCP_LOG_LEVEL` as placeholders.
  - `deploy/k8s/secret.example.yaml`: `entrepataseturnos-mcp-secrets`, with keys `MCP_GOOGLE_CLIENT_SECRET`, `MCP_REDIS_URL` and `MCP_TOKEN_ENCRYPTION_KEY`, each set to `REPLACE_ME`. Add a header comment saying the file must never be applied with real values committed.
- [ ] T051 [P] [US6] Create `deploy/k8s/deployment.yaml` for Deployment `entrepataseturnos-mcp-server`.
  - 2 replicas; image `entrepataseturnos/entrepataseturnos-mcp-server:latest`; `imagePullPolicy: IfNotPresent`; container port 8000.
  - `envFrom` the ConfigMap and the Secret.
  - Probes: `startupProbe` and `livenessProbe` on `/healthz`; `readinessProbe` on `/readyz` (`periodSeconds: 10`, `failureThreshold: 3`).
  - Resources: requests 100m CPU / 128Mi; limits 500m / 256Mi.
  - `securityContext`: `runAsNonRoot`, `runAsUser: 10001`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, all capabilities dropped, and a `RuntimeDefault` seccomp profile.
  - An `emptyDir` mounted at `/tmp`.
- [ ] T052 [P] [US6] Create the remaining manifests.
  - `deploy/k8s/service.yaml`: ClusterIP Service `entrepataseturnos-mcp-server`, port 80 → targetPort 8000.
  - `deploy/k8s/kustomization.yaml`: namespace `entrepataseturnos`; resources namespace, configmap, deployment and service; `images:` entry for `entrepataseturnos/entrepataseturnos-mcp-server` with `newTag: latest`. The secret is created by the operator, as described in the README.
  - `deploy/k8s/redis.yaml`: an optional single-replica Redis 7 Deployment and Service for dev and test clusters, with a comment saying it is not for production.
- [ ] T053 [US6] Write `README.md` (depends on T049–T052). It covers:
  - Overview and architecture: the two endpoints and the OAuth flow with Google.
  - Prerequisites: `uv`, Docker, kubectl, Redis, the API, and the Google web client with its redirect URI.
  - Setup: `uv sync`, then `.env` from `.env.example`, then generating `MCP_TOKEN_ENCRYPTION_KEY`.
  - Local run: `uv run entrepataseturnos-mcp` and connecting an MCP client to `/mcp` and `/public/mcp`.
  - Tests and lint.
  - Docker build and run, using the exact image `entrepataseturnos/entrepataseturnos-mcp-server` with tag `latest` or `TAG=...`.
  - Kubernetes deployment: `kubectl create secret generic ...`, editing the configmap, `kubectl apply -k deploy/k8s`, and the requirement for a public HTTPS ingress plus a recommended rate limit on `/public/mcp`.
  - The configuration reference table from DM §1.
  - The tool catalogue.
  - Known limitations: no pet training; password accounts can't sign in; the shared Google client.
  - A security notes section on secret handling.

**Checkpoint**: The server is deployable. T046–T047 pass, and the image builds.

---

## Phase 6: User Story 2 - Schedule a bath appointment for a pet (Priority: P2)

**Goal**: A signed-in owner can see bath slots, and create, list, view, reschedule and cancel their
own appointments, with confirmation before writes.

**Independent Test**: Quickstart §3 steps 7–8, or the `signed_in_session` fixture tests. A Sunday
shows `open:false`; a confirmed weekday slot creates an appointment; a cancellation is confirmed and
then sent.

### Tests for User Story 2 ⚠️

- [ ] T054 [P] [US2] Write `tests/tools/test_bath.py`. Cover each of the six bath tools with the four required categories:
  - **Valid**: the exact method, path, query and body (`petId`, `startsAt` with offset) are sent, and the output is trimmed per DM §4.
  - **Invalid**: a naive `starts_at`; `starts_at` in the past; `pet_id` 0; a malformed `date`. In each case the API is not called.
  - **API errors**, passed through: `400 invalid_request` with `fields.startsAt`; `409 pet_already_scheduled` with `details.pet_id`; `409 insufficient_capacity`; `409 invalid_status_transition`; `404 appointment_not_found`; `503`.
  - **Authorization**: no bearer; an `owner_id` argument is rejected.
  - **Confirmation**: decline or a missing confirmation results in zero API calls.
  - **Write timeout**: returns `outcome_unknown`.
- [ ] T055 [P] [US2] Write `tests/contract/test_bath_contract.py`. The bath tools must call only these operations:
  - `GET /v1/bath-appointments/availability`
  - `POST /v1/bath-appointments`
  - `GET /v1/bath-appointments/me`
  - `GET|PUT|DELETE /v1/bath-appointments/{id}`

### Implementation for User Story 2

- [ ] T056 [P] [US2] Implement the bath API calls in `src/entrepataseturnos_mcp/api/baths.py`: `slots(token, date)`, `create(token, pet_id, starts_at)`, `list_mine(token, status, from_, to, page, size)`, `get(token, appointment_id)`, `update(token, appointment_id, pet_id, starts_at)` and `delete(token, appointment_id)`.
- [ ] T057 [US2] Implement the six bath tools in `src/entrepataseturnos_mcp/tools/bath.py`, following mcp-tools.md (depends on T056).
  - The tools are `get_bath_slots`, `create_bath_appointment`, `list_my_bath_appointments`, `get_bath_appointment`, `update_bath_appointment` and `cancel_bath_appointment`.
  - Define the domain models there (`BathSlotsInput`, `AppointmentInput`, `AppointmentUpdateInput`, `AppointmentListInput`, `AppointmentRefInput`, `BathDay`, `BathAppointment` and `AppointmentPage`), following DM §3 and §4.
  - Write tools ask for confirmation with the pet name and slot time.
  - Cancel has `destructiveHint=true`.
- [ ] T058 [US2] Register the six bath tools on the authenticated server in `src/entrepataseturnos_mcp/servers.py`.

**Checkpoint**: Bath scheduling works on its own. T054–T055 pass.

---

## Phase 7: User Story 3 - Register a new account (Priority: P3)

**Goal**: Someone without an account can register through `/public/mcp` without signing in. The
server validates the input first, never echoes the password, and confirms with a masked CPF.

**Independent Test**: Quickstart §4. A new registration returns a pending status with a next step;
a duplicate email returns `USER_ALREADY_EXISTS`; the CPF `111.111.111-11` is rejected locally.

### Tests for User Story 3 ⚠️

- [ ] T059 [P] [US3] Write `tests/unit/test_cpf.py`.
  - Valid CPFs are accepted, both formatted and unformatted.
  - Invalid check digits, all-same-digit values (e.g. `11111111111`), the wrong length, and letters are all rejected.
  - Normalization strips `.` and `-`.
  - `mask_cpf("52998224725")` returns `***.***.**7-25`, showing only the last 3 digits.
- [ ] T060 [P] [US3] Write `tests/tools/test_registration.py` against `/public/mcp` with no bearer.
  - **Valid**: exactly one `POST /v1/users` with `{email, name, cpf, password}` and **no** `Authorization` header. The result has `email`, `status` and a `next_step` that mentions email verification and the fact that password accounts can't sign in through the assistant yet.
  - **Invalid**: a bad email, a blank name, an invalid CPF, or a password of 7 characters each return `validation_error`, and the API is not called.
  - **API errors**: 400 `fields` passed through; `409 USER_ALREADY_EXISTS`; `409 CPF_ALREADY_EXISTS`; 500 → `internal_error`. None of them report success.
  - **Confirmation**: the summary contains the masked CPF and no password. If the user declines, no API call is made.
  - **Privacy**: the password value is absent from the result, the error payloads and all captured log records (`caplog`).
- [ ] T061 [P] [US3] Write `tests/integration/test_public_endpoint.py`.
  - The `/public/mcp` tool list is exactly `["register_account"]`.
  - `/mcp` does not list `register_account`.
  - `/public/mcp` requires no bearer.

### Implementation for User Story 3

- [ ] T062 [P] [US3] Implement `register(email, name, cpf, password)` (`POST /v1/users`, never sends a bearer) in `src/entrepataseturnos_mcp/api/users.py`.
- [ ] T063 [US3] Implement the `register_account` tool in `src/entrepataseturnos_mcp/tools/registration.py` (depends on T062).
  - Define `RegisterAccountInput` there, with validators following DM §3: `normalize_cpf`, `is_valid_cpf` and `mask_cpf`.
  - Define `RegistrationResult` there.
  - The confirmation summary is name, email and the masked CPF.
  - The description says the password is sent only to the EntrePatasETurnos API and is never shown.
- [ ] T064 [US3] Register `register_account` on the public server in `src/entrepataseturnos_mcp/servers.py` (`build_public_server`).

**Checkpoint**: Registration works without sign-in. T059–T061 pass.

---

## Phase 8: User Story 4 - Schedule pet training (Priority: P4, placeholder)

**Goal**: Guarantee that no training tool exists (FR-003), and keep the tool catalogue exactly as
contracts/mcp-tools.md defines it.

**Independent Test**: Listing the tools on both endpoints shows exactly the documented set, with no
training, admin or passthrough tools.

- [ ] T065 [US4] Write `tests/contract/test_tool_catalogue.py`.
  - `/mcp` lists exactly the 15 tool names from mcp-tools.md, and `/public/mcp` lists exactly `register_account`.
  - No tool name or description matches `train|adestr|admin|approve|deny|complete|role|http|request|search`.
  - Every tool has a non-empty description and an input schema with `additionalProperties: false`.
  - Every input schema lacks `user_id`, `owner_id`, `account_id` and `role`.
  - Read tools have `readOnlyHint=true`. Write tools have `readOnlyHint=false`, and their descriptions mention confirmation.

**Checkpoint**: The catalogue is locked against unapproved tools.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Security, privacy and quality checks across all stories.

- [ ] T066 [P] Write `tests/integration/test_no_secret_leakage.py`. Run one full successful call and one failing call for every tool, with `caplog` at DEBUG. Assert that no result, error or log record contains any of these:
  - the API access or refresh token values, the MCP bearer, `MCP_GOOGLE_CLIENT_SECRET`, `MCP_TOKEN_ENCRYPTION_KEY` or the Redis password;
  - a test password or an unmasked CPF.
- [ ] T067 [P] Write `tests/contract/test_api_paths.py`. Patch `ApiClient._request` to record every call made across the whole tool test suite, and assert that each path starts with `/v1/` and appears in the upstream operations table in http-endpoints.md (FR-018).
- [ ] T068 Run `uv run ruff check . && uv run ruff format --check . && uv run mypy` and fix every finding in `src/entrepataseturnos_mcp/`.
- [ ] T069 Build the image with `make image` and check it for secrets: `docker history --no-trunc entrepataseturnos/entrepataseturnos-mcp-server:latest` and `docker run --rm --entrypoint sh <image> -c 'env; ls -la /app'` must show no secret values, `.env` or tests. Record the result in `specs/001-mcp-server-foundation/checklists/requirements.md` under Notes.
- [ ] T070 Run `kubectl apply -k deploy/k8s --dry-run=client` to validate the manifests, and fix any errors in the files under `deploy/k8s/`.
- [ ] T071 Run the full quickstart validation in `specs/001-mcp-server-foundation/quickstart.md` (§1–§6) against a dev API, and update `README.md` wherever a step differed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. It blocks every story.
- **US5 Sign-in (Phase 3)**: depends on Foundational. It blocks US1, US2 and the `sign_out` part of US4's catalogue.
- **US1 Booking (Phase 4)**: depends on US5.
- **US6 Deploy (Phase 5)**: depends on Foundational. The probes can start in parallel with US5. The README (T053) is better done after US1, so the tool catalogue is real.
- **US2 Bath (Phase 6)**: depends on US5. It is independent of US1.
- **US3 Registration (Phase 7)**: depends only on Foundational, because the public endpoint has no auth. It can run in parallel with US5.
- **US4 Catalogue guard (Phase 8)**: depends on US1, US2, US3 and US5, since it asserts the full tool list.
- **Polish (Phase 9)**: depends on every story.

### Story Dependency Graph

```text
Setup → Foundational ─┬─→ US5 Sign-in ─┬─→ US1 Booking (MVP) ─┐
                      │                └─→ US2 Bath ──────────┤
                      ├─→ US3 Registration ───────────────────┼─→ US4 Catalogue → Polish
                      └─→ US6 Deploy (probes, image, k8s) ────┘
```

### Within Each Story

- Write the tests first and confirm they fail.
- Then build in this order: API module, then tool module with its models, then registration in `servers.py`.
- Tasks that edit `servers.py` (T037, T045, T058, T064) and `app.py` (T024, T037, T048) are sequential.

## Parallel Opportunities

- **Setup**: T003, T004, T005 and T006.
- **Foundational tests**: T007–T014 are all [P].
- **Foundational implementation**: T015, T016, T017, T019, T020, T021 and T022 run in parallel. T018 follows T015 and T017. T023 follows T022.
- **After Foundational**: US5, US3 and US6 (T046–T052) can proceed in parallel. After US5, US1 and US2 can proceed in parallel.

### Parallel Example: User Story 1

```bash
# Tests together (all different files):
Task: "T038 [US1] tests/tools/test_pets.py"
Task: "T039 [US1] tests/tools/test_accommodation.py"
Task: "T040 [US1] tests/contract/test_accommodation_contract.py"

# API modules together:
Task: "T041 [US1] src/entrepataseturnos_mcp/api/pets.py"
Task: "T042 [US1] src/entrepataseturnos_mcp/api/bookings.py"
```

### Parallel Example: User Story 6

```bash
Task: "T049 [US6] Dockerfile"
Task: "T050 [US6] deploy/k8s/namespace.yaml, configmap.yaml, secret.example.yaml"
Task: "T051 [US6] deploy/k8s/deployment.yaml"
Task: "T052 [US6] deploy/k8s/service.yaml, kustomization.yaml, redis.yaml"
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 (Setup), then Phase 2 (Foundational).
2. Complete Phase 3 (US5 Sign-in), then Phase 4 (US1 Booking).
3. **Stop and validate**: run quickstart §3 steps 1–6 and 9–10.
4. Add Phase 5 (US6) to make the MVP deployable.

### Incremental Delivery

1. MVP (US5 + US1 + US6): a signed-in owner books accommodation through a deployed server.
2. Add US2: bath scheduling.
3. Add US3: public registration.
4. Add US4: lock the catalogue. Then Polish: security sweep and quickstart validation.

---

## Notes

- [P] tasks touch different files and have no dependency on an incomplete task.
- Never add a tool that is not in contracts/mcp-tools.md. The catalogue test (T065) fails if you do.
- Commit after each task or logical group, once git is initialized.
