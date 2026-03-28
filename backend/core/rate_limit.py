import threading
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response, status
from redis import Redis
from redis.exceptions import RedisError

from backend.core.config import get_settings


settings = get_settings()


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at_epoch: int
    retry_after_seconds: int


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._memory_store: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._client: Redis | None = None

    def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        bucket = int(time.time()) // window_seconds
        reset_at_epoch = (bucket + 1) * window_seconds
        redis_key = f"rate-limit:{key}:{bucket}"

        try:
            count = self._check_redis(
                redis_key=redis_key, window_seconds=window_seconds
            )
        except RedisError:
            count = self._check_memory(
                redis_key=redis_key,
                reset_at_epoch=reset_at_epoch,
            )

        remaining = max(limit - count, 0)
        retry_after_seconds = max(reset_at_epoch - int(time.time()), 0)
        return RateLimitResult(
            allowed=count <= limit,
            limit=limit,
            remaining=remaining,
            reset_at_epoch=reset_at_epoch,
            retry_after_seconds=retry_after_seconds,
        )

    def _get_client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    def _check_redis(self, *, redis_key: str, window_seconds: int) -> int:
        client = self._get_client()
        current = int(client.incr(redis_key))
        if current == 1:
            client.expire(redis_key, window_seconds + 1)
        return current

    def _check_memory(self, *, redis_key: str, reset_at_epoch: int) -> int:
        with self._lock:
            current_count, stored_reset = self._memory_store.get(
                redis_key, (0, reset_at_epoch)
            )
            now = int(time.time())
            if stored_reset <= now:
                current_count = 0
                stored_reset = reset_at_epoch
            current_count += 1
            self._memory_store[redis_key] = (current_count, stored_reset)
            self._prune_memory(now)
            return current_count

    def _prune_memory(self, now: int) -> None:
        expired_keys = [
            key for key, (_, reset_at) in self._memory_store.items() if reset_at <= now
        ]
        for key in expired_keys:
            self._memory_store.pop(key, None)


rate_limiter = FixedWindowRateLimiter()


def get_request_identifier(request: Request) -> str:
    session = request.session if hasattr(request, "session") else {}
    username = session.get("operator_username") if isinstance(session, dict) else None
    if username:
        return f"user:{username}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def apply_rate_limit(
    request: Request,
    response: Response,
    *,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    identifier = get_request_identifier(request)
    result = rate_limiter.check(
        key=f"{bucket}:{identifier}",
        limit=limit,
        window_seconds=window_seconds,
    )

    headers = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_at_epoch),
    }
    for key, value in headers.items():
        response.headers[key] = value

    if not result.allowed:
        headers["Retry-After"] = str(result.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests for this action. Please wait and try again.",
            headers=headers,
        )
