"""Redis-backed monthly cost guard."""
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import HTTPException
import redis

from app.config import settings


redis_client = redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
memory_spend: dict[str, float] = defaultdict(float)


def check_budget(user_id: str, estimated_cost: float) -> None:
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    try:
        if redis_client is None:
            raise redis.RedisError("Redis not configured")
        current = float(redis_client.get(key) or 0)

        if current + estimated_cost > settings.monthly_budget_usd:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly budget exceeded. Current: ${current:.4f}",
            )

        redis_client.incrbyfloat(key, estimated_cost)
        redis_client.expire(key, 32 * 24 * 3600)
        return
    except HTTPException:
        raise
    except redis.RedisError:
        current = memory_spend[key]
        if current + estimated_cost > settings.monthly_budget_usd:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly budget exceeded. Current: ${current:.4f}",
            )
        memory_spend[key] += estimated_cost
