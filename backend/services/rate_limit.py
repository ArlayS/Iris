import time
from collections import deque

from fastapi import HTTPException, Request, status

from config import (
    AUTH_INVALID_LOG_INTERVAL,
    AUTH_SESSION_RATE_LIMIT,
    AUTH_SESSION_RATE_WINDOW,
)
from services.request_utils import client_ip


class SlidingWindowLimiter:
    """Limiteur en mémoire (fenêtre glissante). Valable pour un seul worker uvicorn."""

    def __init__(self, max_hits: int, window_seconds: int) -> None:
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._last_gc = time.monotonic()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        self._gc(now)
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.max_hits:
            return False
        hits.append(now)
        return True

    def _gc(self, now: float) -> None:
        if now - self._last_gc < self.window:
            return
        self._last_gc = now
        cutoff = now - self.window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]


class LogThrottle:
    """Autorise au plus 1 log par clé et par intervalle ; borne le nombre de clés suivies."""

    def __init__(self, interval_seconds: int, max_keys: int = 10_000) -> None:
        self.interval = interval_seconds
        self.max_keys = max_keys
        self._seen: dict[str, float] = {}

    def should_log(self, key: str) -> bool:
        now = time.monotonic()
        last = self._seen.get(key)
        if last is not None and now - last < self.interval:
            return False
        if len(self._seen) >= self.max_keys:
            self._seen = {k: t for k, t in self._seen.items() if now - t < self.interval}
            if len(self._seen) >= self.max_keys:
                return False
        self._seen[key] = now
        return True


session_limiter = SlidingWindowLimiter(AUTH_SESSION_RATE_LIMIT, AUTH_SESSION_RATE_WINDOW)
invalid_log_throttle = LogThrottle(AUTH_INVALID_LOG_INTERVAL)


async def session_rate_limit(request: Request) -> None:
    ip = client_ip(request) or "unknown"
    if not session_limiter.allow(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes, réessayez dans un instant.",
            headers={"Retry-After": str(AUTH_SESSION_RATE_WINDOW)},
        )
