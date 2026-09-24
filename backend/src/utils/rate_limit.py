"""
src/utils/rate_limit.py

A deliberately simple in-memory rate limiter, not a production-grade
distributed one. Closes a previously-flagged gap: /upload and /query
had no rate limiting at all.

Limitation, stated plainly: state is per-process. If you ever run more
than one backend instance, each tracks limits independently, so the
effective limit is (instances x limit), not a global one. Fine for a
single free-tier instance; swap for a Redis-backed limiter
(e.g. `slowapi` + Redis) if you ever scale out.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class InMemoryRateLimiter(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_window: int = 20, window_seconds: int = 60):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # /health is exempted — uptime pingers hit it constantly and it
        # does no real work, no reason to count it against the limit.
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[client_ip]

        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.requests_per_window:
            retry_after = int(self.window_seconds - (now - hits[0]))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Too many requests. Limit is {self.requests_per_window} "
                        f"per {self.window_seconds}s. Try again in {max(retry_after, 1)}s."
                    )
                },
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        hits.append(now)
        return await call_next(request)
