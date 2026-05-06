"""Per-IP fixed-window rate limiting."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import Response

from config import RATE_LIMIT_PER_MINUTE
from observability.metrics import inc_rate_limited


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int | None = None):
        super().__init__(app)
        self.per_minute = (
            RATE_LIMIT_PER_MINUTE if per_minute is None else int(per_minute)
        )
        self._hits: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next) -> Response:
        if self.per_minute <= 0:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = self._hits.setdefault(ip, [])
        cutoff = now - 60.0
        window[:] = [t for t in window if t > cutoff]
        if len(window) >= self.per_minute:
            inc_rate_limited()
            return JSONResponse(
                {"error": "rate limit exceeded; retry after a minute"},
                status_code=429,
            )
        window.append(now)
        return await call_next(request)
