# Image for the entrePatasETurnos MCP server.
#
# The server is a client of the API (image `entrepataseturnos/api`, Deployment/Service `eptu-api`
# in deployEntrePatasETurnos). Inside the cluster the API is reached through its ClusterIP Service:
#   http://eptu-api           (Service port 80 -> container port 8080)
# That is the default below; override MCP_API_BASE_URL for local runs, e.g.
#   docker run --env-file .env -e MCP_API_BASE_URL=http://host.docker.internal:8080 ...
#
# Expects a uv project at the build context root: pyproject.toml, uv.lock, src/<package>/.
# Build:  docker build -t entrepataseturnos/mcp:dev .

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------------------
# Build stage: resolve dependencies from the lockfile and install the project into /app/.venv.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first, in their own layer, so source-only changes reuse the cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY README.md* ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------
# Runtime stage: only the virtualenv, no uv, no build tools.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# Same UID/GID the cluster's pod securityContexts use (runAsUser: 10001).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MCP_API_BASE_URL=http://eptu-api

# Secrets (MCP_GOOGLE_CLIENT_SECRET, MCP_REDIS_URL, MCP_TOKEN_ENCRYPTION_KEY) are never baked in:
# pass them at runtime (--env-file .env locally, a Kubernetes Secret in the cluster).

USER app
WORKDIR /app
EXPOSE 8000

# The slim image has no curl; use Python's stdlib against the liveness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request,sys; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\",\"8000\")}/healthz', timeout=3); sys.exit(0)"]

CMD ["entrepataseturnos-mcp"]
