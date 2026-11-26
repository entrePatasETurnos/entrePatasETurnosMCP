# entrePatasETurnos MCP

A study project: an [MCP](https://modelcontextprotocol.io) server for the entrePatasETurnos pet
services, built with the official MCP Python SDK. The server will expose tools that call the
entrePatasETurnos API (image `entrepataseturnos/api`).

## Project files

| File | Purpose |
|---|---|
| `server.py` | The MCP server and its tools |
| `requirements.txt` | Python dependencies, pinned |
| `.env` | Local settings (`MCP_*` variables). Never committed |
| `Dockerfile` | Container image for CI/CD |
| `.dockerignore` | Files kept out of the image |

## Requirements

- Python 3.13
- Node.js (only for the MCP Inspector)

## 1. Set up the environment

```sh
python3 -m venv .venv            # create an isolated environment for this project
source .venv/bin/activate        # activate it (the prompt shows "(.venv)")
pip install -r requirements.txt  # install the dependencies
```

Activate the environment again (`source .venv/bin/activate`) in every new terminal.

> Use `pip install -r requirements.txt`, not `pip install .`: the project has no
> `pyproject.toml`, so `pip install .` fails with *"Directory '.' is not installable"*.

### Dependencies

| Package | Why |
|---|---|
| `mcp` | Official MCP Python SDK: `MCPServer`, the `@mcp.tool()` decorator, the HTTP transport |
| `httpx` | HTTP client for calling the entrePatasETurnos API |
| `uvicorn` | ASGI server that serves the MCP app over HTTP |
| `pydantic-settings` | Reads and validates `MCP_*` settings from the environment |
| `python-dotenv` | Loads `.env` when running locally |

## 2. Run the server

```sh
python server.py
```

The server listens on **http://127.0.0.1:8000/mcp** (streamable HTTP transport). Keep the terminal
open; stop it with `Ctrl+C`.

Host and port come from `MCP_HOST` and `MCP_PORT` (in `.env` or the shell). If port 8000 is busy:

```sh
MCP_PORT=8001 python server.py
```

Opening the URL in a browser shows nothing useful: an MCP server talks to MCP clients. Use one of
the options below.

## 3. Test the server

### Option A: MCP Inspector

In a second terminal:

```sh
npx @modelcontextprotocol/inspector
```

In the browser page that opens:

1. **Transport**: Streamable HTTP
2. **URL**: `http://127.0.0.1:8000/mcp`
3. Click **Connect**, then **Tools → hello**, type a name and click **Run**.

### Option B: Claude Code

With the server running:

```sh
claude mcp add --transport http entrepataseturnos http://127.0.0.1:8000/mcp
```

Start a new Claude Code session and ask it to use the `hello` tool. Run `/mcp` to check the
connection.

## How `server.py` works

```python
mcp = MCPServer(name="entrepataseturnos", instructions="...")

@mcp.tool()
def hello(name: str) -> str:
    """Greet someone. A first tool to check the server works."""
    return f"Olá, {name}! O servidor MCP está funcionando."

mcp.run(transport="streamable-http", host="127.0.0.1", port=8000)
```

- `load_dotenv()` loads `.env` into the environment.
- `MCPServer(...)` creates the server; `instructions` tells the AI what the server is for.
- `@mcp.tool()` turns a Python function into a tool: its arguments become the tool's inputs and
  its docstring becomes the description the AI reads.
- `mcp.run(transport="streamable-http", ...)` serves it over HTTP, the same transport used in Docker
  and Kubernetes.

> In `mcp` 2.x, `FastMCP` was renamed to `MCPServer` (`from mcp.server.mcpserver import MCPServer`).
> Tutorials written for 1.x use `from mcp.server.fastmcp import FastMCP`, which no longer works.

## Roadmap

- [x] Step 1: dependencies (`requirements.txt`)
- [x] Step 2: minimal server with a `hello` tool
- [x] Step 3: test with MCP Inspector and Claude Code
- [ ] Step 4: a tool that calls `entrepataseturnos/api` with `httpx`
- [ ] Step 5: build and run with Docker

> The `Dockerfile` still installs from `pyproject.toml`/`uv.lock` with `uv`. It will be switched to
> `requirements.txt` in step 5; until then `docker build` fails.
