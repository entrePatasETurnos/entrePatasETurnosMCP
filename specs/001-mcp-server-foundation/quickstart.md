# Quickstart & Validation: EntrePatasETurnos MCP Server Foundation

This guide proves the feature works end to end. The configuration it uses is listed in
[data-model.md §1](data-model.md); the endpoints are in
[contracts/http-endpoints.md](contracts/http-endpoints.md); the tools are in
[contracts/mcp-tools.md](contracts/mcp-tools.md).

## Prerequisites

- `uv` ≥ 0.11 and Docker.
- `kubectl` with access to a test cluster. It is needed for steps 5 and 6.
- A running EntrePatasETurnos API, for example the API repository's `./run.sh --dev`, which listens
  on `http://localhost:8080`.
- Redis. Locally, `docker run -d -p 6379:6379 redis:7-alpine`.
- Access to the Google web OAuth client that the API uses. Add this redirect URI to it:
  `http://localhost:8000/oauth/google/callback`.

## 1. Set up and run the automated tests

```bash
uv sync                      # creates .venv and installs locked dependencies
uv run ruff check . && uv run mypy src
uv run pytest
```

**Expected**: all tests pass. They cover valid input, invalid input, API errors and authorization
boundaries for every tool.

## 2. Run locally

```bash
cp .env.example .env         # fill in the values; .env is git- and docker-ignored
export MCP_TOKEN_ENCRYPTION_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
uv run entrepataseturnos-mcp
curl -s localhost:8000/healthz   # {"status":"ok"}
curl -s localhost:8000/readyz    # {"status":"ready",...}
```

**Negative checks**:
- Unset `MCP_API_BASE_URL`. The server exits non-zero with
  `missing/invalid setting: MCP_API_BASE_URL`, and no secret values appear in the output.
- Stop the API. `/healthz` stays `200`, and `/readyz` returns `503` with `"api":"fail"`.

## 3. Sign in and use the tools (User Stories 1, 2 and 5)

1. Add the server to an MCP client that supports OAuth, using the URL `http://localhost:8000/mcp`.
   The MCP Inspector works: `npx @modelcontextprotocol/inspector`.
2. The client opens a browser to Google. Sign in with a test Google account.
3. List the tools. There should be 15 tools on `/mcp`, and none of them is a training tool.
4. Call `list_my_pets`. Only the test account's pets should be returned.
5. Call `get_accommodation_free_dates` with `pets=1` and `nights=2`.
6. Call `create_accommodation_booking`. The client should show a confirmation prompt.
   - If you decline: the result is `cancelled_by_user`, and no booking exists in the API.
   - If you accept: a `Booking` with status `registered` is returned.
7. Call `get_bath_slots` for a Sunday. The result should show `open: false`.
8. Book a weekday slot with `create_bath_appointment`, then cancel it with
   `cancel_bath_appointment`. Both should ask for confirmation.
9. Wait more than 15 minutes, then call `list_my_pets` again. It should still succeed, because
   the server refreshes the API session.
10. Call `sign_out`. The next call should fail with a 401 that prompts sign-in.

**Expected**: no token, password or secret appears in any tool result, or in the server logs
(`grep -Ei 'token|password|secret'` finds only redacted markers).

## 4. Register an account (User Story 3)

1. Connect a client to `http://localhost:8000/public/mcp`. No sign-in is needed.
2. Call `register_account` with a new email and a valid CPF, and confirm. The result has a status
   like `PENDING_EMAIL_VERIFICATION`, and its `next_step` mentions email verification.
3. Repeat with the same email. The result should be `USER_ALREADY_EXISTS`.
4. Call it with the CPF `111.111.111-11`. The server rejects it with `validation_error`, and the
   API receives no request.

## 5. Build and run the container

```bash
docker build -t entrepataseturnos/entrepataseturnos-mcp-server:latest .
docker run --rm --env-file .env -p 8000:8000 entrepataseturnos/entrepataseturnos-mcp-server:latest
docker history --no-trunc entrepataseturnos/entrepataseturnos-mcp-server:latest | grep -Ei 'secret|token|password'   # no matches
```

## 6. Deploy to Kubernetes

```bash
kubectl create namespace entrepataseturnos
kubectl -n entrepataseturnos create secret generic entrepataseturnos-mcp-secrets \
  --from-literal=MCP_GOOGLE_CLIENT_SECRET=... \
  --from-literal=MCP_REDIS_URL=redis://... \
  --from-literal=MCP_TOKEN_ENCRYPTION_KEY=...
# edit deploy/k8s/configmap.yaml (API URL, public URL, Google client id)
kubectl apply -k deploy/k8s
kubectl -n entrepataseturnos rollout status deploy/entrepataseturnos-mcp-server
```

**Expected**:
- The pods become Ready within 60 seconds (SC-007).
- Port-forwarding the Service lets an MCP client list the tools.
- A signed-in user's calls succeed while their requests alternate between the two replicas.
