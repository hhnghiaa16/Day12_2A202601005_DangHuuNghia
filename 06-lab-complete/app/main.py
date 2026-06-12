"""Production AI Agent for Day 12 lab."""
import json
import logging
import signal
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import redis
import uvicorn

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget
from app.rate_limiter import check_rate_limit
from utils.mock_llm import ask as llm_ask

STATIC_DIR = Path(__file__).resolve().parent / "static"


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_redis_available = False
_request_count = 0
_error_count = 0

redis_client = redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
memory_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(default="default", min_length=1, max_length=100)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    history_length: int
    model: str
    timestamp: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _redis_available
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    if redis_client is not None:
        try:
            redis_client.ping()
            _redis_available = True
        except redis.RedisError as exc:
            _redis_available = False
            logger.warning(json.dumps({"event": "redis_unavailable", "error": str(exc)}))
    else:
        logger.warning(json.dumps({"event": "redis_not_configured", "storage": "memory"}))
    _is_ready = True
    logger.info(json.dumps({"event": "ready", "redis": _redis_available}))

    yield

    _is_ready = False
    if redis_client is not None:
        redis_client.close()
    logger.info(json.dumps({"event": "shutdown"}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.time() - start) * 1000, 1),
        }))
        return response
    except Exception:
        _error_count += 1
        raise


@app.get("/config", tags=["Info"])
def get_config():
    """Return demo config for the UI.

    AGENT_API_KEY = password to call this chatbot (intentionally shared for demo).
    OPENAI_API_KEY is NEVER returned here — it stays server-side only.
    """
    return {
        "api_key": settings.agent_api_key,   # chatbot access key (demo-safe)
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "llm_model": settings.llm_model,
        "environment": settings.environment,
    }


@app.get("/", tags=["Info"])
def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (requires X-API-Key)",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(body: AskRequest, request: Request, api_key: str = Depends(verify_api_key)):
    user_id = body.user_id
    check_rate_limit(user_id)

    input_tokens = max(1, len(body.question.split()) * 2)
    check_budget(user_id, estimated_cost=(input_tokens / 1000) * settings.input_cost_per_1k)

    history = get_history(user_id)
    prompt = body.question if not history else f"Previous turns: {history}\nQuestion: {body.question}"

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "question_length": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
        "api_key_prefix": api_key[:4],
    }))

    answer = llm_ask(prompt)
    output_tokens = max(1, len(answer.split()) * 2)
    check_budget(user_id, estimated_cost=(output_tokens / 1000) * settings.output_cost_per_1k)

    history_length = append_history(user_id, {"q": body.question, "a": answer})

    return AskResponse(
        user_id=user_id,
        question=body.question,
        answer=answer,
        history_length=history_length,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "storage": "redis" if _redis_available else "memory",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Not ready")
    if redis_client is None:
        return {"ready": True, "redis": "not_configured", "storage": "memory"}
    try:
        redis_client.ping()
        return {"ready": True, "redis": "ok", "storage": "redis"}
    except redis.RedisError:
        return {"ready": True, "redis": "unavailable", "storage": "memory"}


@app.get("/metrics", tags=["Operations"])
def metrics(_api_key: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "monthly_budget_usd": settings.monthly_budget_usd,
        "storage": "redis" if _redis_available else "memory",
    }


def get_history(user_id: str) -> list[str]:
    if redis_client is not None:
        try:
            return redis_client.lrange(f"history:{user_id}", -10, -1)
        except redis.RedisError:
            pass
    return list(memory_history[user_id])[-10:]


def append_history(user_id: str, item: dict) -> int:
    serialized = json.dumps(item)
    if redis_client is not None:
        try:
            key = f"history:{user_id}"
            redis_client.rpush(key, serialized)
            redis_client.ltrim(key, -20, -1)
            redis_client.expire(key, 7 * 24 * 3600)
            return redis_client.llen(key)
        except redis.RedisError:
            pass
    memory_history[user_id].append(serialized)
    return len(memory_history[user_id])


def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
