<!--
Sync Impact Report
==================
Version change: (unversioned template) → 1.0.0
Bump rationale: Initial ratification; all placeholders replaced with project-specific governance.

Modified principles (template placeholder → new title):
- [PRINCIPLE_1_NAME] → I. The API Is the Source of Truth
- [PRINCIPLE_2_NAME] → II. Expose Specified User Workflows
- [PRINCIPLE_3_NAME] → III. Preserve Identity and Authorization
- [PRINCIPLE_4_NAME] → IV. Confirm User-Requested Changes
- [PRINCIPLE_5_NAME] → V. Validate Inputs and Report Errors

Added principles:
- VI. Protect Personal Information
- VII. Keep the API Contract Explicit
- VIII. Verify Every Tool

Added sections:
- Purpose and Scope (from [SECTION_2_NAME])
- Development Workflow and Quality Gates (from [SECTION_3_NAME])
- Governance (filled from [GOVERNANCE_RULES])

Removed sections: none

Dependent templates: not modified by this command (they read the constitution at runtime).
- .specify/templates/plan-template.md: "Constitution Check" gate should evaluate Principles I–VIII.
- .specify/templates/spec-template.md: specs should name the workflow, API operations, and
  confirmation requirements per Principles II, IV, VII.
- .specify/templates/tasks-template.md: tasks should include the four test categories in Principle VIII.

Deferred TODOs: none
-->

# EntrePatasETurnos MCP Server Constitution

## Core Principles

### I. The API Is the Source of Truth

- The MCP server MUST call the EntrePatasETurnos API for all application data and operations.
- The MCP server MUST NOT connect directly to the API database or duplicate API business rules.
- The MCP server MUST report an operation as successful only after receiving a successful API
  response.

**Rationale**: A single authority for data and business rules prevents divergence between the
MCP server and the application, and guarantees that what the user is told matches reality.

### II. Expose Specified User Workflows

- The server MUST expose only narrowly defined tools for workflows listed in approved feature
  specifications.
- The initial workflows are: user registration, accommodation booking, and scheduling bath
  appointments for pets.
- Pet-training tools MUST be added only after the API supports that workflow and an approved
  feature specification defines it.
- The server MUST NOT expose arbitrary HTTP requests, unrestricted database access, or
  administrative API operations by default.

**Rationale**: A small, deliberate tool surface limits what a model can do on a user's behalf and
keeps every capability traceable to an approved specification.

### III. Preserve Identity and Authorization

- The server MUST use the authenticated user identity supplied through a trusted authentication
  flow.
- The server MUST NOT trust a user ID, role, or account ID supplied as an ordinary
  model-generated tool argument.
- The server MUST preserve the API's authentication and authorization checks and MUST NOT bypass
  them.
- API credentials and user access tokens MUST remain server-side and MUST NOT appear in
  model-visible tool results or logs.

**Rationale**: Tool arguments are produced by a model and can be manipulated; identity and
authorization must come from trusted channels so one user cannot act as another.

### IV. Confirm User-Requested Changes

- Before submitting a booking, registration, or appointment request, the assistant MUST show the
  user the relevant details and obtain the user's confirmation.
- Read-only tools MAY run without confirmation.
- The MCP server MUST NOT approve or deny bookings, schedule appointments for another account, or
  perform other privileged actions unless a future approved specification explicitly authorizes
  them.

**Rationale**: State-changing actions affect real reservations and appointments; explicit user
confirmation prevents unintended or hallucinated submissions.

### V. Validate Inputs and Report Errors

- Every tool MUST have a clear name, a description, and a typed input schema.
- The server MUST validate inputs before calling the API.
- The server MUST return API errors accurately and MUST NOT invent data or claim that a failed
  operation succeeded.
- Tool responses MUST include only the information needed for the user's request.

**Rationale**: Typed, validated inputs reduce bad API calls, and faithful error reporting keeps the
model and the user from acting on false information.

### VI. Protect Personal Information

- The server MUST request, transmit, and return only the personal information required for the
  selected workflow.
- The server MUST NOT log passwords, access tokens, secrets, or unnecessary personal or pet
  details.

**Rationale**: Data minimization limits exposure of user and pet information through model
context, transport, and logs.

### VII. Keep the API Contract Explicit

- API paths, request fields, response fields, and error behavior MUST follow the API's documented
  contracts.
- All API calls MUST use the API's versioned routes.
- API contract changes MUST be reflected in the affected MCP tools and their specifications.

**Rationale**: An explicit, versioned contract keeps the MCP server predictable and makes API
changes visible instead of silently breaking tools.

### VIII. Verify Every Tool

- Each tool MUST have tests for valid input, invalid input, API errors, and authorization
  boundaries.
- Tests MUST verify that the server calls the documented API operation and does not report
  success when the API fails.

**Rationale**: Tests are the enforcement mechanism for Principles I, III, V, and VII; without them
those guarantees cannot be demonstrated.

## Purpose and Scope

- **Purpose**: Build a Python MCP server that lets MCP clients access approved EntrePatasETurnos
  workflows through the existing EntrePatasETurnos API.
- **Language**: The server MUST be implemented in Python.
- **Integration boundary**: The server is a client of the EntrePatasETurnos API only; it owns no
  application data store of its own for EntrePatasETurnos domain data (Principle I).
- **In scope**: User registration, accommodation booking, and pet bath appointment scheduling, as
  defined by approved feature specifications.
- **Out of scope until specified**: Pet training, administrative operations, approval or denial of
  bookings, and any action on behalf of another account.

## Development Workflow and Quality Gates

- Every new or changed tool MUST originate from an approved feature specification that names the
  workflow, the API operations it calls, and whether user confirmation is required.
- Implementation plans MUST pass a Constitution Check against Principles I–VIII before design and
  again after design.
- Pull requests that add or change tools MUST include the tests required by Principle VIII, and
  those tests MUST pass before merge.
- Reviews MUST check that no credentials, tokens, or unnecessary personal data appear in tool
  results or logs (Principles III and VI).

## Governance

- This constitution supersedes other project practices. Where a guideline conflicts with it, the
  constitution prevails.
- Amendments MUST be proposed in writing with a rationale, reviewed, and recorded in this file with
  an updated Sync Impact Report.
- Versioning follows semantic versioning:
  - MAJOR: Backward-incompatible removal or redefinition of a principle or governance rule.
  - MINOR: A new principle or section, or materially expanded guidance.
  - PATCH: Clarifications, wording, or typo fixes with no semantic change.
- Every specification, plan, and code review MUST verify compliance with this constitution. Any
  deviation MUST be documented and justified in the relevant plan's complexity tracking.

**Version**: 1.0.0 | **Ratified**: 2026-11-20 | **Last Amended**: 2026-11-20
