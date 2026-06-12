"""Redis-backed sliding window rate limiting."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException
import redis

from app.config import settings


redis_client = redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
memory_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(user_id: str) -> None:
    now = time.time()
    key = f"rate:{user_id}"
    window_seconds = 60

    try:
        if redis_client is None:
            raise redis.RedisError("Redis not configured")
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        pipe.zcard(key)
        _, current = pipe.execute()

        if current >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": str(window_seconds)},
            )

        redis_client.zadd(key, {str(now): now})
        redis_client.expire(key, window_seconds)
        return
    except HTTPException:
        raise
    except redis.RedisError:
        window = memory_windows[user_id]
        while window and window[0] < now - window_seconds:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": str(window_seconds)},
            )
        window.append(now)
