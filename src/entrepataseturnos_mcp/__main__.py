"""Entry point: ``entrepataseturnos-mcp`` / ``python -m entrepataseturnos_mcp``."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .config import load_settings
from .logging import configure_logging


def main() -> None:
    settings = load_settings()  # exits 2, naming bad variables, if configuration is invalid
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
        server_header=False,
    )


if __name__ == "__main__":
    main()
