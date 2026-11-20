# Research: EntrePatasETurnos MCP Server Foundation

**Feature**: `001-mcp-server-foundation` | **Date**: 2026-11-20

Facts about the upstream API come from the sibling repository `entrePatasETurnosAPI` (Java/Quarkus),
read on 2026-11-20. SDK facts come from inspecting the `mcp` 2.3.0 wheel.

---

## R1. Python version and project tooling

- **Decision**: Python 3.13, managed with `uv`. Use a `src/` layout and a `pyproject.toml` with
  `uv.lock` committed. The local `.venv` comes from `uv sync`.
- **Rationale**: The user required `uv`. Python 3.13 is installed locally and is supported by every
  dependency below. The `src/` layout prevents tests from importing the working tree by accident.
- **Alternatives considered**:
  - Python 3.12: no reason to choose an older interpreter.
  - Poetry: rejected because the user required `uv`.

## R2. MCP SDK and transport

- **Decision**: Use the official `mcp` SDK, pinned as `mcp>=2.3,<3`, through
  `mcp.server.mcpserver.MCPServer`. In 2.x, `FastMCP` was renamed `MCPServer`.
- **Transport**: Streamable HTTP via `MCPServer.streamable_http_app(stateless_http=True,
  json_response=True)`, served by `uvicorn`.
- **Rationale**:
  - The user required Streamable HTTP.
  - Stateless mode keeps no MCP session state in process memory, so any replica can serve any
    request. Kubernetes can then run more than one replica without sticky sessions (spec, User
    Story 5, scenario 7).
  - The tools only do request/response work, so server-initiated streams are not needed.
    Elicitation (R8) still works within a single request's response.
- **Alternatives considered**:
  - Stateful sessions with sticky routing: fragile across rollouts.
  - Pinning `mcp<2`: 1.x is legacy, and the 2.x auth API is the supported one.
- **Note**: `mcp` 2.x depends on `httpx2` internally. Our API client uses `httpx` as the user
  required. The two packages coexist.

## R3. How users sign in (spec FR-006 to FR-006e)

### Constraints found in the API

- **Only Google sign-in.** `POST /v1/auth/sessions/google` takes `{idToken, deviceName?}` and
  returns `{sessionId, accessToken, accessTokenExpiresAt, refreshToken, refreshTokenExpiresAt,
  userId, ...}`.
  - Access tokens last 15 minutes.
  - Refresh tokens last 30 days and rotate on each use.
  - Refresh is `POST /v1/auth/sessions/{id}/refresh {refreshToken}`.
  - Sign-out is `DELETE /v1/auth/sessions/{id}`.
- **Single Google audience.** The API accepts a Google ID token only if its `aud` equals the one
  configured `entrepataseturnos.auth.google.client-id`. That is the existing Google *web* OAuth
  client.
- **No service credential.** The API has no API key and no client-credentials grant.

### Decision

The MCP server acts as the **OAuth 2.1 authorization server** for its MCP clients. It uses the SDK's
`OAuthAuthorizationServerProvider` with `AuthSettings`, and **federates sign-in to Google**.

1. **Discovery.** The MCP client finds the server's AS metadata, registers itself dynamically
   (RFC 7591), and starts `/authorize` with PKCE S256.
2. **`authorize()`** stores a *pending authorization* in Redis under a random `state`. It holds the
   client id, redirect URI, PKCE challenge, scopes and the client's state, with a 10-minute TTL. It
   then returns a redirect to Google's authorization endpoint (`response_type=code`,
   `scope=openid email profile`, its own PKCE).
3. **Google callback.** Google redirects to a custom route `GET /oauth/google/callback`. The server
   exchanges the code at Google's token endpoint using the web client's id and secret, and receives
   an `id_token`.
4. **API session.** The server calls `POST /v1/auth/sessions/google` with
   `{idToken, deviceName: "EntrePatasETurnos MCP"}`. The server does **not** verify the ID token
   itself; the API does (Principle I). The response's tokens are stored as an encrypted
   **API session record** in Redis.
5. **Back to the client.** The server issues an MCP authorization code (5-minute TTL, single use),
   bound to the pending authorization and the session record, and redirects to the client's
   redirect URI.
6. **Token exchange.** The client exchanges the code at `/token` and receives:
   - an opaque MCP access token, 1-hour TTL;
   - an opaque MCP refresh token, TTL capped at the API refresh token's expiry.

   Only SHA-256 hashes of these tokens are stored as keys.
7. **Per request.** The SDK's bearer middleware calls `load_access_token()`, which resolves to the
   session record. Tools obtain an API access token through `SessionService.api_token()`. That
   method refreshes the API token when it expires within 60 seconds.
   - A Redis lock (`SET NX PX`) per session prevents parallel rotation.
   - A caller that loses the lock waits for the winner's result. A `409 refresh_in_progress` is
     retried once.
   - When the API returns `401 invalid_refresh_token`, the session is deleted and the tool returns
     `sign_in_required`.
8. **Sign-out.** The SDK revocation endpoint and the `sign_out` tool both call
   `DELETE /v1/auth/sessions/{id}`, then delete the session and every MCP token that points to it.

### Google OAuth client

- **Decision**: Reuse the **existing Google web OAuth client**, whose id is the API's configured
  audience. Add the MCP server's callback URL to that client's authorized redirect URIs. The client
  id and secret reach the MCP server only through a Kubernetes Secret.
- **Rationale**: This needs no API change, because the API accepts only one audience.
- **Alternative considered**: A dedicated Google client for the MCP server. It would need an API
  change so the API accepts a list of audiences. Recorded as a follow-up in the plan's risks.

### Tokens at rest

- **Decision**: Encrypt the API session record's token fields with AES-256-GCM, using
  `cryptography` and a 32-byte key from `MCP_TOKEN_ENCRYPTION_KEY`. Store MCP tokens only as hashes.
- **Rationale**: Meets FR-006d. Someone who reads Redis gets neither usable API tokens nor usable MCP
  tokens.

### Alternatives considered for sign-in

- Passing the user's API token through from the client: rejected by the user (Q2 = A).
- A separate authorization server, such as Keycloak: adds operating cost for no gain, since the API
  only trusts Google anyway.

## R4. Shared session store

- **Decision**: **Redis**, via `redis` with its asyncio client, reached through `MCP_REDIS_URL`.
  Every record has a TTL that matches its lifetime.
- **Rationale**: Redis offers TTLs and atomic `SET NX` for refresh locks, and it is easy to run in
  Kubernetes. The stored data is small and short-lived.
- **Alternatives considered**:
  - PostgreSQL: heavier, and needs migrations for ephemeral data.
  - In-memory storage: breaks with more than one replica (FR-006d).
  - Encrypted cookies or JWTs as MCP tokens: these cannot be revoked server-side (spec edge case:
    a stolen token replayed after sign-out).
- **Deployment**: Production uses an operator-provided Redis, such as a managed instance or a Helm
  release. `deploy/k8s/redis.yaml` provides a single-replica Redis for dev and test clusters only.

## R5. REST API client

- **Decision**: Use one shared `httpx.AsyncClient` with:
  - `base_url = MCP_API_BASE_URL`;
  - `httpx.Timeout(connect=3, read=MCP_API_TIMEOUT_SECONDS (default 10), write=10, pool=5)`;
  - limits of 20 connections;
  - an `X-Correlation-Id` header on every request.

  Each endpoint gets a typed method, and paths are built only from `/v1/...` constants.
- **Rationale**: Meets FR-013 and FR-018. Typed per-operation methods mean no arbitrary-request
  helper exists (FR-002).
- **Retries**: `GET` requests are retried once on connect errors only. Writes are never retried.
- **Timeouts on writes**: these map to the error `outcome_unknown` (FR-013).

## R6. Error model

- **API error shapes**:
  - `{error, message}`
  - `{error:"invalid_request", message, fields:{...}}`
  - conflict extras such as `petIds` and `petId`
- **Decision**: Raise `ToolError` with a JSON payload shaped as
  `{error_code, message, fields?, details?, http_status}`. The API's `error` code and Portuguese
  field messages are passed through unchanged (FR-012).
- **Local codes added by the server**:
  - `validation_error`: input rejected before calling the API.
  - `sign_in_required`
  - `upstream_timeout`
  - `outcome_unknown`: a write that timed out.
  - `upstream_unavailable`: connection failure or 5xx without a body.
  - `upstream_invalid_response`: malformed JSON.
  - `session_store_unavailable`
- **Rationale**: The model and the user see exactly what failed (Principle V).

## R7. Input validation

- **Decision**: Use Pydantic v2 models (the SDK already depends on Pydantic) as tool parameter types.
  Each tool's JSON input schema is generated from those models.
- **Rules mirrored from the API** (see data-model.md):
  - datetimes must carry an offset;
  - check-out must be after check-in;
  - check-in must not be in the past;
  - 1 to 50 pet ids, all positive;
  - 1 to 90 nights;
  - date ranges of at most 366 days;
  - CPF must pass the check-digit algorithm;
  - passwords must be at least 8 characters;
  - page size from 1 to 100.
- **Rationale**: Meets FR-010 and gives fast, precise feedback. The API stays authoritative and
  re-validates everything.

## R8. Confirmation before writes (Principle IV, FR-005)

- **Decision**: Use two layers.
  1. **Elicitation.** When the client supports elicitation, every write tool calls `ctx.elicit()`
     with a summary of the details and a boolean `confirm` field. Anything other than an accepted
     `confirm=true` aborts with `cancelled_by_user`, and the API is not called.
  2. **Fallback.** When the client lacks elicitation, the write tool requires
     `user_confirmed: true` in its input.
     - Its description says the assistant MUST show the details and get the user's explicit "yes"
       first.
     - The tool annotations set `readOnlyHint=false`, plus `destructiveHint=true` for cancel.
- **Rationale**: Elicitation puts the confirmation in front of the human, not the model. The
  fallback still forces a deliberate step, and its tests prove the API is not called without it.
- **Alternative considered**: A two-step "preview, then commit" flow with a server-issued nonce.
  Rejected as more complex for no extra assurance, because a model could chain the two calls.

## R9. Registration without signing in (User Story 3)

- **Problem**: When MCP auth is on, the SDK protects the whole MCP endpoint. Someone without an
  account cannot sign in, and Google sign-in would create the account anyway. The registration
  tool would therefore be unreachable for the user it exists for.
- **Decision**: Serve a second, **unauthenticated MCP endpoint at `/public/mcp`**. It is a separate
  `MCPServer` instance with exactly one tool, `register_account`, which calls `POST /v1/users`
  without a user token.
  - The authenticated endpoint `/mcp` does **not** offer `register_account`.
  - Both apps are mounted in one Starlette application. Its lifespan runs both session managers.
- **Rationale**: Meets User Story 3 without weakening auth on `/mcp`. The API endpoint is already
  public (`@PermitAll`) and rate-limits verification emails.
- **Alternatives considered**:
  - Offering `register_account` on the authenticated endpoint: unusable by people without an
    account.
  - Dropping registration: it is an initial workflow in the constitution.
- **Caveat**: An account made by password registration cannot sign in to `/mcp` yet, because the API
  has no password sign-in. The tool's result says so (spec Assumptions).

## R10. Health and readiness

- **Decision**:
  - `GET /healthz`: liveness. Returns `200 {"status":"ok"}` while the event loop responds, with no
    upstream checks.
  - `GET /readyz`: readiness. Returns `200` only when all of these hold:
    - settings loaded;
    - Redis answers `PING` within 1 second;
    - `GET /v1/info` on the API returns 2xx within 2 seconds.

    Otherwise it returns `503` with the name of each failing check and no secrets.
  - Results are cached for 5 seconds to keep probes cheap.
- **Rationale**: Meets FR-020 and FR-021, and the spec's "API unreachable" scenario.
  `/v1/info` is `@PermitAll`.

## R11. Configuration

- **Decision**: Use `pydantic-settings` with the prefix `MCP_`. `SecretStr` fields hide secrets
  from `repr` and logs. Validation runs at startup, and the server exits non-zero naming each
  missing setting (FR-016). The variables are listed in data-model.md, section 1.
- **Rationale**: Gives typed environment configuration with redacted secrets.

## R12. Logging

- **Decision**: Structured JSON logs to stdout, using standard `logging` with a JSON formatter.
  - A redaction filter drops `authorization`, `password`, `*token*`, `cpf`, `idToken`, `code`
    and `secret` keys.
  - Request bodies are never logged.
  - Log lines carry the tool name, correlation id, API status and duration.
- **Rationale**: Meets Principle VI and FR-008.

## R13. Container image

- **Decision**: A multi-stage Dockerfile.
  - **Builder**: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` runs
    `uv sync --frozen --no-dev --no-editable`.
  - **Runtime**: `python:3.13-slim-bookworm` with only `/app/.venv` copied in.
  - The runtime runs as non-root user `10001`, with `EXPOSE 8000` and
    `CMD ["entrepataseturnos-mcp"]`.
  - A `.dockerignore` excludes `.env*`, `.venv`, `tests` and `specs`.
- **Image name**: `entrepataseturnos/entrepataseturnos-mcp-server:${TAG:-latest}`, built through
  `make image TAG=...` or a plain `docker build -t` command.
- **Rationale**: Meets FR-017 and FR-023. The image is small and contains no secrets.

## R14. Kubernetes manifests

- **Decision**: Put plain YAML in `deploy/k8s/`, applied with `kubectl apply -k`.
  - `kustomization.yaml`
  - `configmap.yaml`: non-secret settings.
  - `secret.example.yaml`: placeholders only, named `*.example` so it is never applied as-is.
    The README shows `kubectl create secret generic`.
  - `deployment.yaml`:
    - 2 replicas;
    - `runAsNonRoot`, `readOnlyRootFilesystem`, all capabilities dropped;
    - `livenessProbe` `/healthz`, `readinessProbe` `/readyz`, plus a startupProbe;
    - resource requests and limits;
    - `envFrom` the ConfigMap and the Secret.
  - `service.yaml`: ClusterIP, port 80 → 8000.
  - `redis.yaml`: optional, dev only.
- **Ingress**: Not included. The README explains that the OAuth flow needs a public HTTPS URL
  (`MCP_PUBLIC_BASE_URL`) routed to the Service.
- **Rationale**: Meets FR-022 with tooling that works without Helm.

## R15. Testing

- **Decision**: `pytest` with `anyio` (bundled with the SDK) for async tests.
  - `respx` mocks `httpx`, so tests assert the exact method, path and body sent to the API.
  - `fakeredis` stands in for Redis.
  - Tools are exercised end-to-end in-process through the SDK's client against the Starlette app.
  - Each tool is tested for valid input, invalid input (no API call made), API errors (each
    documented code, plus timeout and 5xx), and authorization boundaries:
    - no token;
    - expired session;
    - refresh failure;
    - identity arguments rejected;
    - a foreign pet id rejected by the API.
- **Static checks**: `ruff` (lint and format) and `mypy --strict` on `src/`.
- **Rationale**: Meets Principle VIII and FR-024.
