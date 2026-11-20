# Implementation Plan: EntrePatasETurnos MCP Server Foundation

**Branch**: `001-mcp-server-foundation` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-mcp-server-foundation/spec.md`

## Summary

Build a Python MCP server that runs in Kubernetes as a network service. It lets signed-in pet owners
view their pets, book accommodation and schedule bath appointments, and it lets new users register.
Every operation goes through the versioned EntrePatasETurnos REST API (`/v1`).

**Sign-in.** The server is an OAuth 2.1 authorization server for its MCP clients and federates
sign-in to Google. It exchanges the Google ID token for an API session and keeps that session,
encrypted, in Redis. Clients receive only opaque MCP tokens.

**Endpoints.**
- **`/mcp`** (authenticated): 15 tools, served over stateless Streamable HTTP.
- **`/public/mcp`** (unauthenticated): `register_account` only.

**Safety.** Inputs are validated against the API's rules before any call. Every write requires user
confirmation, through elicitation or an explicit `user_confirmed` flag. API errors are passed
through accurately.

**Out of scope.** Pet training is deferred, and no tool is added for it.

**Delivery.** The project ships with a Dockerfile (image
`entrepataseturnos/entrepataseturnos-mcp-server:latest`), kustomize manifests, `/healthz` and
`/readyz` probes, and a README.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**:
- `mcp>=2.3,<3` (`MCPServer`, Streamable HTTP, OAuth AS provider)
- `httpx>=0.28` (API client)
- `pydantic>=2.12`
- `pydantic-settings>=2.16`
- `redis>=8.1` (asyncio)
- `cryptography>=50` (AES-GCM)
- `uvicorn>=0.54`
- `starlette`, which comes with `mcp`

**Dev Dependencies**: `pytest>=9`, `respx>=0.23`, `fakeredis>=2.40`, `ruff`, `mypy`

**Package Management**: `uv`, with `pyproject.toml` and `uv.lock` committed and a local `.venv`

**Storage**: Redis for auth and session state only, with a TTL on every key. There is no domain
storage.

**Testing**: `pytest` with anyio, `respx` for HTTP mocking, `fakeredis`, and in-process MCP client
tests

**Target Platform**: Linux container (python:3.13-slim) on Kubernetes, x86_64 or arm64

**Project Type**: Network web service (MCP server)

**Performance Goals**: Tool latency stays within the API timeout plus 1 s at p99 (SC-008). Readiness
is reached in under 60 s (SC-007). Load is modest, in the tens of concurrent users.

**Constraints**:
- No secrets in the source code or the image.
- No identity is taken from tool arguments.
- Every API call uses `/v1` routes.
- Stateless MCP transport, so the server can run more than one replica.
- The container runs as non-root with a read-only root filesystem.

**Scale/Scope**: 16 tools on two endpoints, 1 API client, and 1 OAuth provider. The server starts
with 2 replicas.

All unknowns are resolved in [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-design | Post-design |
|---|---|---|---|
| I. API is source of truth | No database access. Success is reported only on an API 2xx. | ✅ Spec FR-011 | ✅ Redis holds only auth state. Tools map 1:1 to API operations ([mcp-tools.md](contracts/mcp-tools.md)). Writes are never retried. A timed-out write returns `outcome_unknown`. |
| II. Specified workflows only | Narrow tools only. No admin, passthrough or training tools. | ✅ FR-001–003 | ✅ The "Not exposed" list in mcp-tools.md. Each API operation has its own typed client method, and there is no generic request helper. |
| III. Identity and authorization | Identity comes from a trusted flow. No identity arguments. Tokens stay on the server. | ✅ FR-006–009 | ✅ OAuth with Google sign-in (research R3). Input models use `extra="forbid"` and have no identity fields. Tokens are encrypted or hashed in Redis and redacted from logs. |
| IV. Confirm changes | Writes are confirmed. Reads are not. No privileged actions. | ✅ FR-005 | ✅ Elicitation, with a `user_confirmed` fallback (R8). Tests assert that the API is not called when confirmation is missing. |
| V. Validate and report errors | Typed schemas, validation before the call, accurate errors, minimal output. | ✅ FR-004, 010–014 | ✅ Pydantic inputs ([data-model.md](data-model.md) §3), trimmed outputs (§4), and an error payload (§5). |
| VI. Protect personal information | Minimal data, nothing sensitive in logs. | ✅ FR-008, 014 | ✅ A redaction filter, no request-body logging, a masked CPF in the confirmation prompt, and the password never echoed. |
| VII. Explicit API contract | Documented contracts and versioned routes. | ✅ FR-018 | ✅ The upstream operations table in [http-endpoints.md](contracts/http-endpoints.md) cites the API's documented routes. A contract test pins each path and method. |
| VIII. Verify every tool | Valid, invalid, API-error and authorization tests per tool. | ✅ FR-024 | ✅ Testing strategy in R15, with a per-tool test matrix in `tests/tools/`. |

**Result**: PASS, with no violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-server-foundation/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── mcp-tools.md     # Tool catalogue, API mapping, errors, confirmation
│   └── http-endpoints.md# MCP, OAuth, Google callback, probes, upstream operations
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
pyproject.toml                  # uv project; script entry point entrepataseturnos-mcp
uv.lock
.python-version                 # 3.13
.env.example                    # variable names only, no values for secrets
.gitignore / .dockerignore
Dockerfile
Makefile                        # image / run / test helpers (TAG ?= latest)
README.md

src/entrepataseturnos_mcp/
├── __init__.py
├── __main__.py                 # entry point: load settings, build app, run uvicorn
├── config.py                   # Settings (pydantic-settings, MCP_ prefix, SecretStr)
├── logging.py                  # JSON formatter and redaction filter
├── app.py                      # Starlette composition: /mcp, /public/mcp, OAuth routes, probes, lifespan
├── health.py                   # /healthz, /readyz with cached checks
├── api/
│   ├── client.py               # httpx.AsyncClient wrapper: timeouts, correlation id, error mapping
│   ├── errors.py               # ApiError, UpstreamTimeout, OutcomeUnknown, ...
│   ├── auth.py                 # sessions: google, refresh, delete
│   ├── users.py                # POST /v1/users
│   ├── pets.py                 # GET /v1/pets
│   ├── bookings.py             # /v1/accommodation-bookings operations used by the tools
│   └── baths.py                # /v1/bath-appointments operations used by the tools
├── auth/
│   ├── crypto.py               # AES-GCM encryption and token hashing
│   ├── store.py                # Redis repositories (session, client, pending, code, tokens)
│   ├── provider.py             # OAuthAuthorizationServerProvider implementation
│   ├── google.py               # Google authorize URL, code exchange, callback route
│   └── session.py              # SessionService.api_token(): refresh with lock; sign_out
├── tools/
│   ├── models.py               # input and output models, validators (CPF, offsets, ranges)
│   ├── errors.py               # ApiError to ToolError payload
│   ├── confirm.py              # elicitation and the user_confirmed fallback
│   ├── registration.py         # register_account (public server)
│   ├── pets.py
│   ├── accommodation.py
│   ├── bath.py
│   └── account.py              # sign_out
└── servers.py                  # builds the authenticated and public MCPServer instances and registers tools

tests/
├── conftest.py                 # settings fixture, respx router, fakeredis, in-process MCP clients
├── unit/                       # config, crypto, validators, error mapping, logging redaction
├── auth/                       # provider flow, Google callback, refresh lock, revocation
├── tools/                      # one module per tool group: valid, invalid, API errors, authz
├── contract/                   # every API call uses a documented /v1 path and method; no training tool; tool list
└── integration/                # app wiring: probes, 401 on /mcp, /public/mcp unauthenticated

deploy/k8s/
├── kustomization.yaml
├── namespace.yaml
├── configmap.yaml
├── secret.example.yaml         # placeholders only; not listed in kustomization
├── deployment.yaml
├── service.yaml
└── redis.yaml                  # optional, dev/test only; not in the default kustomization
```

**Structure Decision**: A single Python package in a `src/` layout. It has an `api/` layer (one
typed module per API resource), an `auth/` layer (OAuth provider and session store), and a `tools/`
layer (thin MCP adapters with no business rules). Deployment files live in `deploy/k8s/`.

## Key Risks and Follow-ups

1. **Shared Google client.** Reusing the API's Google web client means a new redirect URI must be
   added in Google Cloud Console for every MCP deployment URL. A dedicated client would need the API
   to accept several audiences, which is an API change and a future feature.
2. **Password accounts.** Accounts created through `register_account` cannot sign in to `/mcp`
   until the API supports password sign-in or account linking.
3. **Elicitation support varies by client.** The `user_confirmed` fallback depends on the
   assistant behaving honestly. This is accepted, and it is documented in the tool descriptions.
4. **Public registration endpoint.** `/public/mcp` exposes a public API operation. Rate limiting
   relies on the API and on the ingress, where the README recommends a limit.
5. **API security issue in another repository.** The API repository commits a Resend API key
   (`application.properties:180`). It should be rotated. This is outside this feature.

## Complexity Tracking

No constitution violations to justify. Two design choices add complexity, and each is explained in
research.md:

- **Two MCP endpoints**: research R9.
- **The server acting as its own OAuth authorization server**: research R3.
