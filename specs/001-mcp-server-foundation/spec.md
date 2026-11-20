# Feature Specification: EntrePatasETurnos MCP Server Foundation

**Feature Branch**: `001-mcp-server-foundation`

**Created**: 2026-11-20

**Status**: Draft

**Input**: User description: "Create a Python project for the EntrePatasETurnos MCP server. Use `uv`
to manage dependencies and a local virtual environment. Build an MCP server that exposes tools for
the EntrePatasETurnos REST API. Implement a REST API client using `httpx`; read the API base URL and
credentials from environment variables. Provide MCP tools for user registration, accommodation
bookings, bath scheduling, and pet training scheduling. Use the Streamable HTTP transport so the
server can run as a network service in Kubernetes. Include clear error handling, request timeouts,
and input validation. Include a Dockerfile and Kubernetes deployment and service manifests. Expose
health and readiness endpoints for Kubernetes probes. Do not include API credentials or other
secrets in the source code or Docker image. Include a README with setup, local run, Docker
build/run, and Kubernetes deployment instructions. Build the Docker image as
`entrepataseturnos/entrepataseturnos-mcp-server`, tag `latest` unless another tag is specified."

## User Scenarios & Testing *(mandatory)*

Actors:

- **Pet owner**: a person using an AI assistant (an MCP client) to manage their EntrePatasETurnos
  account, pets, accommodation bookings, and bath appointments.
- **Operator**: the person who builds, configures, and deploys the MCP server to the cluster.

### User Story 1 - Book accommodation for my pets through an assistant (Priority: P1)

A signed-in pet owner asks their assistant to find dates when the facility can take their pets and
to book a stay. The assistant lists the owner's pets, checks which dates are free for the requested
number of pets and nights, shows the owner the booking details, and submits the booking only after
the owner confirms. The owner can also list, view, change, or cancel their own bookings while they
are still awaiting review.

**Why this priority**: Accommodation booking is the core paid service and the most valuable
workflow to automate.

**Independent Test**: With a test account that owns at least one pet, ask the assistant to book a
stay; verify the availability lookup, the confirmation prompt, the created booking in the API, and
that the booking appears in the owner's booking list.

**Acceptance Scenarios**:

1. **Given** a signed-in owner with two pets, **When** they ask for free dates for both pets for 3
   nights next month, **Then** the assistant returns the days that fit, as reported by the API.
2. **Given** the owner confirmed the shown details (pets, check-in, check-out), **When** the
   booking is submitted, **Then** the assistant reports success with the booking identifier and
   status returned by the API.
3. **Given** the facility has no capacity for the requested period, **When** the booking is
   submitted, **Then** the assistant reports that capacity is insufficient and does not claim a
   booking was made.
4. **Given** a booking that is still awaiting review, **When** the owner asks to cancel it and
   confirms, **Then** the booking is cancelled and the assistant says so.
5. **Given** a booking that was already approved, **When** the owner asks to cancel it, **Then**
   the assistant reports that the booking can no longer be changed.
6. **Given** a pet that belongs to another account, **When** the assistant tries to include it in a
   booking, **Then** the request is rejected and no booking is created.

---

### User Story 2 - Schedule a bath appointment for a pet (Priority: P2)

A signed-in pet owner asks for open bath slots on a given day, picks one, confirms, and the
appointment is created for one of their pets. The owner can also list, view, reschedule, or cancel
their own appointments while they are awaiting review.

**Why this priority**: Second core service; shares the same identity and confirmation patterns as
booking, so it builds directly on Story 1.

**Independent Test**: With a test account that owns a pet, ask for slots on an open day, schedule
one, and verify it in the API and in the owner's appointment list.

**Acceptance Scenarios**:

1. **Given** a signed-in owner, **When** they ask for bath slots on an open day, **Then** the
   assistant lists the slot times and whether each is available.
2. **Given** a closed day (e.g. Sunday), **When** slots are requested, **Then** the assistant says
   the day is closed.
3. **Given** the owner confirmed pet and slot, **When** the appointment is submitted, **Then** the
   assistant reports the created appointment with its time and status from the API.
4. **Given** the pet already has an appointment at that time, **When** the appointment is
   submitted, **Then** the assistant reports the conflict and does not claim success.
5. **Given** a requested time that is not an offered slot, **When** the appointment is submitted,
   **Then** the request is rejected with a clear explanation.

---

### User Story 3 - Register a new account (Priority: P3)

A person without an account asks the assistant to register them. The assistant collects the
required details (name, email, CPF, password), shows the non-secret details for confirmation, and
submits the registration. The person is told to verify their email.

**Why this priority**: Needed for new users, but most users arrive already signed in, and
registration is a one-time action.

**Independent Test**: Register a new test identity through the assistant and verify the API
reports the account as pending email verification.

**Acceptance Scenarios**:

1. **Given** valid details, **When** the person confirms, **Then** the account is created and the
   assistant tells them to verify their email.
2. **Given** an email or CPF already in use, **When** the registration is submitted, **Then** the
   assistant reports which field conflicts and does not claim success.
3. **Given** an invalid CPF or a password shorter than 8 characters, **When** the registration is
   submitted, **Then** it is rejected before reaching the API, with a field-level message.
4. **Given** any registration attempt, **When** results and logs are inspected, **Then** the
   password appears in neither.

---

### User Story 4 - Schedule pet training (Priority: P4, placeholder — no tool in this feature)

Pet owners will eventually ask the assistant to schedule training sessions for their pets. The
EntrePatasETurnos API does not support training yet, so constitution Principle II forbids a
training tool. This feature adds **no** training tool and no "not available" stub. It only keeps
the tool design open, so a later feature can add training next to bookings and bath appointments
without restructuring the server.

**Why this priority**: The user requested it, but it is blocked on the API. It is recorded so the
intent is not lost.

**Independent Test**: Verify that the server's tool list contains no training tool.

**Acceptance Scenarios**:

1. **Given** the deployed server, **When** an MCP client lists the tools, **Then** no
   training-related tool is present.
2. **Given** an owner asks the assistant to schedule training, **When** the assistant looks at the
   available tools, **Then** it finds no training tool and can tell the owner the service is not
   available through the assistant.

**Activation conditions** (for a future feature): the API ships versioned training endpoints with a
documented contract, and an approved feature specification defines the training tools.

---

### User Story 5 - Sign in to use the assistant (Priority: P1)

A pet owner connects their assistant to the EntrePatasETurnos MCP server for the first time. The
server asks them to sign in with their Google account in the browser. After sign-in, the assistant
can act on the owner's behalf, and the owner's API session stays on the server. The session renews
itself while it is valid. The owner can sign out, which ends the API session.

**Why this priority**: Every tool except registration needs a signed-in user. Without sign-in, no
other P1 story works.

**Independent Test**: Connect an MCP client to the server, complete Google sign-in with a test
account, call a read-only tool, and verify that the API saw that user and that no token appeared in
the client.

**Acceptance Scenarios**:

1. **Given** a client that has not signed in, **When** it calls a tool that requires a user,
   **Then** the server refuses and starts or points to the sign-in flow.
2. **Given** an owner who completes Google sign-in, **When** the client calls "list my pets",
   **Then** the result shows only that owner's pets.
3. **Given** a signed-in owner whose API access token has expired, **When** they call a tool,
   **Then** the server renews the session and the call succeeds without a new sign-in.
4. **Given** the API refuses to renew the session (revoked or expired), **When** the owner calls a
   tool, **Then** the server reports that they must sign in again.
5. **Given** the email on the Google account belongs to a password-registered account that is not
   linked, **When** sign-in completes, **Then** the server reports that the account must be linked
   first and creates no session.
6. **Given** a signed-in owner, **When** they sign out, **Then** the API session is ended and later
   tool calls require a new sign-in.
7. **Given** two instances of the server, **When** consecutive requests from one signed-in owner
   reach different instances, **Then** both succeed.

---

### User Story 6 - Deploy and operate the server in the cluster (Priority: P1)

An operator builds the server image, supplies configuration and secrets through the cluster, and
deploys it. The cluster checks the server's health and readiness and sends traffic only to
instances that are ready. The operator can also run it locally for development by following the
README.

**Why this priority**: Without a deployable, observable service, none of the user stories reach
users. This story is developed alongside Story 1.

**Independent Test**: Build the image, deploy it with the supplied manifests to a test cluster
with the API reachable, and verify probes pass and an MCP client can list the tools.

**Acceptance Scenarios**:

1. **Given** the image is built, **When** its contents are inspected, **Then** it contains no
   credentials, tokens, or secret values.
2. **Given** the server is deployed with valid configuration, **When** the cluster probes it,
   **Then** health and readiness both report OK.
3. **Given** required configuration (e.g. the API address) is missing, **When** the server starts,
   **Then** it fails fast with a clear message naming the missing setting, without printing secret
   values.
4. **Given** the API is unreachable, **When** readiness is probed, **Then** readiness reports not
   ready while health still reports alive.
5. **Given** a new developer follows the README, **When** they set up and run the server locally,
   **Then** an MCP client can connect and list the tools.

---

### Edge Cases

- The API does not respond within the timeout: the tool reports a timeout and does not claim the
  operation succeeded or failed definitively for writes.
- The user's API session expires mid-conversation: the server renews it with the stored refresh
  token; if renewal is refused, the tool reports that the user must sign in again.
- Two calls from the same user try to renew the session at the same time (the API answers "refresh
  in progress"): only one renewal takes effect, and the other call uses its result or retries once.
- The session store is unavailable: signed-in tools fail with a clear "temporarily unavailable"
  message, and readiness reports not ready.
- An MCP client credential is stolen or replayed after sign-out: it is rejected because the
  server-side session no longer exists.
- The API returns an unexpected or malformed response: the tool reports an upstream error without
  inventing data.
- The API returns field-level validation errors (in Portuguese): the tool returns them per field,
  unchanged in meaning.
- A model-generated argument tries to supply a user, owner, or account identifier: it is not
  accepted; identity comes only from the authenticated session.
- Times are given without a timezone offset: they are rejected before the API call, or interpreted
  in the facility's time zone (America/Sao_Paulo), stated explicitly to the user.
- A requested date range exceeds the API's limits (e.g. more than 366 days): rejected before the
  API call with a clear message.
- Changing or cancelling a booking or appointment that is no longer awaiting review: the API's
  refusal is reported as-is.
- A list result spans several pages: the tool returns one page and states how to request the next.

## Requirements *(mandatory)*

### Functional Requirements

**Tools and workflows**

- **FR-001**: The server MUST expose tools only for these workflows: account registration, listing
  the user's own pets, accommodation availability and free dates, creating/listing/viewing/updating/
  cancelling the user's own accommodation bookings, bath slot availability, and creating/listing/
  viewing/updating/cancelling the user's own bath appointments.
- **FR-002**: The server MUST NOT expose tools that approve, deny, or complete bookings or
  appointments, manage other users, change roles, search other users' pets, or make arbitrary
  requests to the API.
- **FR-003**: The server MUST NOT expose any pet-training tool, stub, or placeholder tool in this
  feature. Training tools are deferred until the API supports training and a specification defines
  them (User Story 4).
- **FR-004**: Every tool MUST have a clear name, a description that states whether it changes data,
  and a typed input schema.
- **FR-005**: Tools that create, change, or cancel data MUST state in their description that the
  assistant must show the details to the user and obtain confirmation before calling them.

**Identity and authorization**

- **FR-006**: Every tool except registration MUST act as the authenticated end user. The MCP
  server MUST run the sign-in flow itself, using the MCP authorization flow with Google as the
  identity provider. It MUST exchange the resulting Google identity for an API session through the
  API's Google session operation, and keep that API session on the server.
- **FR-006a**: The MCP client MUST receive only an MCP-server-issued credential that is bound to the
  server-side session. API access and refresh tokens and Google tokens MUST never be sent to the
  MCP client or the model.
- **FR-006b**: The server MUST renew the API session through the API's refresh operation when the
  access token has expired or is about to expire. When renewal fails, it MUST report that the user
  must sign in again.
- **FR-006c**: The server MUST provide sign-out, which ends the API session and invalidates the
  MCP client's credential.
- **FR-006d**: Server-side session data MUST be stored outside any single instance, so that any
  instance can serve any signed-in user. Stored tokens MUST be protected at rest.
- **FR-006e**: API sign-in errors MUST be reported accurately: invalid assertion, account link
  required, account unavailable, and provider unavailable.
- **FR-007**: Tools MUST NOT accept user, owner, account, or role identifiers as inputs; identity
  MUST come only from the authenticated session.
- **FR-008**: Access tokens, refresh tokens, passwords, and other secrets MUST NOT appear in tool
  results or logs.
- **FR-009**: The server MUST leave all authorization decisions to the API and MUST NOT bypass
  them.

**Validation, errors, timeouts**

- **FR-010**: The server MUST validate inputs against the API's documented rules before calling the
  API (e.g. dates with explicit offsets, check-out after check-in, 1–50 pets, 1–90 nights, valid
  CPF, password at least 8 characters, page size at most 100).
- **FR-011**: The server MUST report success only when the API returns a success response.
- **FR-012**: The server MUST return API errors with their error code and meaning preserved,
  including per-field validation messages and conflict details (e.g. which pets are already booked).
- **FR-013**: Every API call MUST have a bounded timeout, set by configuration with a sensible
  default; on timeout the tool MUST report that the outcome is unknown for write operations.
- **FR-014**: Tool results MUST include only the fields needed for the request (e.g. no internal
  links, reviewer ids, or other users' data).

**Configuration and secrets**

- **FR-015**: The API base address, timeouts, Google sign-in client settings, session-store
  connection settings, and token-protection keys MUST be read from environment variables at
  startup.
- **FR-016**: The server MUST refuse to start when required configuration is missing and MUST name
  the missing setting without printing secret values.
- **FR-017**: No credentials or secret values MUST be present in source code, the container image,
  or committed manifests; manifests MUST reference secrets supplied by the cluster.
- **FR-018**: All API calls MUST use the API's versioned routes (`/v1/...`).

**Operations**

- **FR-019**: The server MUST run as a network service that MCP clients reach over HTTP using
  streaming responses, suitable for running several instances behind a cluster service.
- **FR-020**: The server MUST expose a liveness endpoint that reports alive while the process can
  serve requests, independent of the API.
- **FR-021**: The server MUST expose a readiness endpoint that reports ready only when the
  configuration is valid and both the API and the session store are reachable.
- **FR-022**: The project MUST include a container build definition, cluster deployment and service
  manifests, and a README covering setup, local run, image build/run, and cluster deployment.
- **FR-023**: The container image MUST be named `entrepataseturnos/entrepataseturnos-mcp-server`
  and tagged `latest` unless another tag is specified.
- **FR-024**: Every tool MUST have automated tests for valid input, invalid input, API errors, and
  authorization boundaries, verifying the documented API operation is called and failures are not
  reported as success.

### Key Entities

- **User session**: the signed-in end user's API session. It holds the API session id, access and
  refresh tokens, and their expiry times, and is linked to the MCP client credential the server
  issued. It is kept in shared server-side storage and never shown to the client or the model.
- **MCP client credential**: what the MCP server issues to the client after sign-in. It is opaque
  to the client, can be revoked, and identifies a user session only on the server side.
- **Registration**: name, email, CPF, password; results in an account pending email verification.
- **Pet**: owned by one user; id, name, species, gender, age. Needed to choose pets for bookings and
  appointments.
- **Accommodation booking**: owner, pets, check-in, check-out, nights, status (registered,
  approved, denied, completed). Only "registered" bookings can be changed or cancelled by the owner.
- **Accommodation availability / free dates**: capacity and per-day free places for a date range,
  number of pets, and nights.
- **Bath appointment**: owner, one pet, start and end time, status (same lifecycle as bookings).
- **Bath slot**: a start time on a given day with availability; one-hour duration; facility closed
  on Sundays.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A signed-in owner can go from "book a stay" to a confirmed booking in under 3 minutes
  of conversation.
- **SC-002**: 100% of state-changing tool calls in acceptance tests are preceded by a user
  confirmation step.
- **SC-003**: 0 instances of tokens, passwords, or secrets found in tool results, logs, or the
  container image during security review.
- **SC-004**: 100% of tools have passing tests for valid input, invalid input, API errors, and
  authorization boundaries.
- **SC-005**: In fault-injection tests, 0 failed or timed-out API operations are reported as
  successful.
- **SC-006**: A new developer can run the server locally and connect a client in under 15 minutes
  using only the README.
- **SC-007**: A fresh deployment to the cluster becomes ready within 60 seconds of start when the
  API is reachable.
- **SC-008**: Tool responses return within the configured timeout plus 1 second in 99% of calls.
- **SC-009**: A first-time owner can sign in and make their first successful tool call in under
  2 minutes.
- **SC-010**: Signed-in owners are asked to sign in again no more often than the API's 30-day
  refresh-session lifetime requires, unless they sign out or the session is revoked.

## Assumptions

- The user's stated technical choices are binding constraints for planning: Python, `uv` for
  dependencies and a local virtual environment, `httpx` for the API client, MCP Streamable HTTP
  transport, a Dockerfile, and Kubernetes Deployment and Service manifests.
- The API is the existing EntrePatasETurnos API with versioned routes under `/v1` and no `/api`
  prefix; contracts come from the API repository's `specs/*/contracts/rest-api.md` because it has no
  OpenAPI document.
- Registration is a public API operation and needs no signed-in user. Accounts created by password
  registration cannot yet sign in to the API (only Google sign-in exists); the assistant states this
  after registration.
- Accommodation is a single facility with a shared capacity; there is no catalogue of rooms to
  choose from.
- Times sent to the API carry an explicit offset; the facility time zone is America/Sao_Paulo.
- Pet creation, editing, and photos are out of scope for this feature; listing the user's own pets
  is included because bookings and appointments need pet ids.
- Email verification and resending verification are out of scope for this feature.
- A shared session store reachable from the cluster is available. The plan chooses which one; the
  manifests reference its connection settings through cluster secrets.
- A Google OAuth client is registered for the MCP server, with redirect addresses that match the
  deployment. Its client secret is supplied only through cluster secrets.
- Only Google sign-in is supported, because it is the only sign-in method the API offers. Accounts
  that registered with a password cannot use the assistant's signed-in tools until the API supports
  password sign-in or account linking.
- Pet training is deferred. See User Story 4 for when it can be added.
