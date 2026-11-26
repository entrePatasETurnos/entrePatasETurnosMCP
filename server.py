"""Minimal entrePatasETurnos MCP server (study version).

Run locally:   python server.py
It listens on http://127.0.0.1:8000/mcp (streamable HTTP transport).
"""

import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

# Reads .env (if present) into os.environ, so MCP_* settings work locally.
load_dotenv()

mcp = MCPServer(
    name="entrepataseturnos",
    instructions="Tools for the entrePatasETurnos pet services.",
)


@mcp.tool()
def hello(name: str) -> str:
    """Greet someone. A first tool to check the server works."""
    return f"Olá, {name}! O servidor MCP está funcionando."


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
    )
