"""Kubernetes probes (research R10): ``/healthz`` (liveness) and ``/readyz`` (readiness)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse

CACHE_SECONDS = 5.0

Check = Callable[[], Awaitable[object]]


async def healthz(_: Request) -> JSONResponse:
    """Alive while the event loop answers. Never checks dependencies."""
    return JSONResponse({"status": "ok"})


class Readiness:
    def __init__(self, checks: dict[str, tuple[Check, float]]) -> None:
        self._checks = checks
        self._cached: tuple[float, dict[str, str]] | None = None

    async def _run(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for name, (check, timeout) in self._checks.items():
            try:
                with anyio.fail_after(timeout):
                    await check()
                results[name] = "ok"
            except Exception:  # noqa: BLE001 - any failure means "not ready"
                results[name] = "fail"
        return results

    async def results(self) -> dict[str, str]:
        now = time.monotonic()
        if self._cached is not None and now - self._cached[0] < CACHE_SECONDS:
            return self._cached[1]
        results = await self._run()
        self._cached = (now, results)
        return results

    async def endpoint(self, _: Request) -> JSONResponse:
        checks = {"settings": "ok", **(await self.results())}
        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status_code=200 if ready else 503,
        )
