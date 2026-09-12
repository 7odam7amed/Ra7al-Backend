from abc import ABC, abstractmethod
from collections import defaultdict
import logging
import threading
import time
from typing import Any
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Redis Lua script for atomic sliding-window rate limiting
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clearBefore = now - window

redis.call('ZREMRANGEBYSCORE', key, '-inf', clearBefore)
local currentRequests = redis.call('ZCARD', key)

if currentRequests < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window + 1)
    return {0, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retryAfter = 1
    if oldest and #oldest >= 2 then
        local oldestScore = tonumber(oldest[2])
        retryAfter = math.max(1, math.ceil(oldestScore + window - now))
    end
    return {1, retryAfter}
end
"""


class BaseRateLimiterStore(ABC):
    """Abstract base class for sliding-window rate limiter stores."""

    @abstractmethod
    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int]:
        """Check if request exceeds rate limit.

        Returns:
            tuple[bool, int]: (is_limited, retry_after_seconds)
        """
        pass

    @abstractmethod
    def reset(self, key: str | None = None) -> None:
        """Reset timestamps for a specific key or all keys."""
        pass


class InMemoryRateLimiterStore(BaseRateLimiterStore):
    """Thread-safe in-memory store for rate limiting sliding-window request timestamps."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            timestamps = [t for t in self._store[key] if t > window_start]
            self._store[key] = timestamps

            if len(timestamps) >= max_requests:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now) + 1)
                return True, retry_after

            self._store[key].append(now)
            return False, 0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is not None:
                self._store.pop(key, None)
            else:
                self._store.clear()


# Backward compatibility alias
RateLimiterStore = InMemoryRateLimiterStore


class RedisRateLimiterStore(BaseRateLimiterStore):
    """Atomic Redis-backed sliding-window rate limiter store for distributed deployments."""

    def __init__(self, redis_url: str | None = None, redis_client: Any | None = None) -> None:
        self.redis_url = redis_url
        self._client = redis_client
        self._script: Any = None
        self._fallback_store = InMemoryRateLimiterStore()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import redis
            settings = get_settings()
            url = self.redis_url or settings.REDIS_URL or "redis://localhost:6379/0"
            self._client = redis.Redis.from_url(url, decode_responses=True)
            return self._client
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}. Falling back to in-memory store.")
            return None

    def _get_script(self, client: Any) -> Any:
        if self._script is None and client is not None:
            self._script = client.register_script(SLIDING_WINDOW_LUA)
        return self._script

    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int]:
        client = self._get_client()
        if client is None:
            return self._fallback_store.is_rate_limited(key, max_requests, window_seconds)

        try:
            script = self._get_script(client)
            now = time.time()
            redis_key = f"ratelimit:{key}"
            result = script(keys=[redis_key], args=[now, window_seconds, max_requests])
            is_limited = bool(result[0])
            retry_after = int(result[1])
            return is_limited, retry_after
        except Exception as exc:
            logger.warning(f"Redis rate limiter error: {exc}. Falling back to in-memory limiter.")
            return self._fallback_store.is_rate_limited(key, max_requests, window_seconds)

    def reset(self, key: str | None = None) -> None:
        client = self._get_client()
        self._fallback_store.reset(key)
        if client is None:
            return

        try:
            if key is not None:
                client.delete(f"ratelimit:{key}")
            else:
                cursor = 0
                while True:
                    cursor, keys = client.scan(cursor=cursor, match="ratelimit:*", count=100)
                    if keys:
                        client.delete(*keys)
                    if cursor == 0:
                        break
        except Exception as exc:
            logger.warning(f"Redis reset error: {exc}")


class DelegatingRateLimiterStore(BaseRateLimiterStore):
    """Dynamic dispatcher that routes rate limiting to Redis or InMemory based on active Settings."""

    def __init__(self) -> None:
        self.in_memory = InMemoryRateLimiterStore()
        self._redis_store: RedisRateLimiterStore | None = None

    def _get_active_store(self) -> BaseRateLimiterStore:
        settings = get_settings()
        if settings.RATE_LIMIT_BACKEND == "redis" and settings.REDIS_URL:
            if self._redis_store is None or self._redis_store.redis_url != settings.REDIS_URL:
                self._redis_store = RedisRateLimiterStore(settings.REDIS_URL)
            return self._redis_store
        return self.in_memory

    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int]:
        return self._get_active_store().is_rate_limited(key, max_requests, window_seconds)

    def reset(self, key: str | None = None) -> None:
        self.in_memory.reset(key)
        if self._redis_store is not None:
            self._redis_store.reset(key)


limiter_store = DelegatingRateLimiterStore()


def get_client_ip(request: Request) -> str:
    """Extract client IP securely by verifying trusted reverse proxies.

    Prevents IP spoofing via headers when requests originate directly from untrusted clients.
    """
    settings = get_settings()
    trusted_proxies = set(settings.TRUSTED_PROXIES)

    direct_ip = request.client.host if request.client and request.client.host else "127.0.0.1"

    # Only trust proxy forwarding headers if the immediate connection is from a configured trusted proxy
    if direct_ip in trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Leftmost entry represents original client in standard proxy chains
            for part in forwarded.split(","):
                clean = part.strip()
                if clean:
                    return clean

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

    return direct_ip


class RateLimiter:
    """FastAPI dependency enforcing sliding-window rate limiting per client IP."""

    def __init__(
        self,
        times: int,
        seconds: int,
        key_prefix: str = "global",
    ) -> None:
        self.times = times
        self.seconds = seconds
        self.key_prefix = key_prefix

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        if not settings.RATE_LIMIT_ENABLED:
            return

        client_ip = get_client_ip(request)
        rate_key = f"{self.key_prefix}:{client_ip}"

        limited, retry_after = limiter_store.is_rate_limited(
            key=rate_key,
            max_requests=self.times,
            window_seconds=self.seconds,
        )

        if limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        """Reset this limiter's tracked timestamps."""
        limiter_store.reset()


# Pre-configured endpoint rate limiters
login_rate_limiter = RateLimiter(times=5, seconds=60, key_prefix="login")
register_rate_limiter = RateLimiter(times=5, seconds=60, key_prefix="register")
upload_id_card_rate_limiter = RateLimiter(times=10, seconds=60, key_prefix="upload_id_card")
upload_bus_image_rate_limiter = RateLimiter(times=20, seconds=60, key_prefix="upload_bus_image")
boarding_scan_rate_limiter = RateLimiter(times=60, seconds=60, key_prefix="boarding_scan")


