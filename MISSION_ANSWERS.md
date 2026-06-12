# Day 12 Lab - Mission Answers

> **Student:** Đặng Hữu Nghĩa  
> **Student ID:** 2A202601005  
> **Date:** 2026-06-12

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `app.py`

1. **Hardcoded API key** — `API_KEY = "sk-1234567890abcdef"` nằm thẳng trong code. Nếu commit lên Git, key bị lộ hoàn toàn.
2. **Port cố định** — `app.run(port=8000)` không đọc từ environment. Khi deploy lên cloud (Railway, Render) platform assign port động qua `$PORT`.
3. **Debug mode luôn bật** — `debug=True` in ra stack trace, tiết lộ cấu trúc nội bộ cho attacker.
4. **Không có health check** — Platform không biết khi nào app ready/unhealthy để restart.
5. **Không có graceful shutdown** — Process bị kill đột ngột, request đang xử lý bị mất.
6. **Dùng `print()` thay vì logging** — Không có timestamp, level, format; khó phân tích log trên cloud.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode trong code | Env vars (`os.getenv`) | Secrets không lọt vào Git; dễ thay đổi mà không rebuild |
| Health check | Không có | `GET /health` → `{"status":"ok"}` | Platform tự restart khi app unhealthy |
| Logging | `print()` | JSON structured logging | Dễ query, filter, alert trên log aggregator |
| Shutdown | Đột ngột (SIGKILL) | Graceful — hoàn thành request rồi mới exit | Không mất request đang xử lý |
| Port | Fixed `8000` | `int(os.getenv("PORT", 8000))` | Railway/Render assign port động |
| Debug | `debug=True` | `debug=False` | Ẩn stack trace khỏi user cuối |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11-slim` — dùng Debian slim để nhỏ hơn full image (~50MB vs ~900MB)
2. **Working directory:** `/app` — tất cả file app được copy và chạy trong `/app`
3. **Tại sao COPY requirements.txt trước:** Docker layer caching — nếu chỉ code thay đổi mà requirements không đổi, layer `pip install` được reuse từ cache, build nhanh hơn nhiều
4. **CMD vs ENTRYPOINT:**
   - `ENTRYPOINT` = lệnh cố định, không override được khi `docker run`
   - `CMD` = lệnh mặc định, có thể override: `docker run image python other_script.py`
   - Dùng cả hai: `ENTRYPOINT ["python"]` + `CMD ["app.py"]` cho phép override argument

### Exercise 2.2: Image size

```
my-agent:develop    ~200 MB   (single-stage, full deps)
my-agent:advanced   ~160 MB   (multi-stage, chỉ runtime deps)
```

### Exercise 2.3: Multi-stage build analysis

- **Stage 1 (builder):** Install tất cả dependencies (bao gồm build tools như gcc, setuptools) vào `/root/.local`
- **Stage 2 (runtime):** Copy ONLY `/root/.local` từ builder — không có build tools, không có pip cache
- **Tại sao nhỏ hơn:** Build tools (gcc ~30MB, headers...) không có trong final image; pip cache bị bỏ

### Exercise 2.4: Docker Compose stack

Architecture:
```
Client → Nginx (port 80) → agent:8000 (có thể scale ×3)
                                 ↓
                            Redis:6379
```

Services được start: `nginx`, `agent` (×1 hoặc ×3), `redis`  
Communicate qua Docker internal network: `agent` → `redis:6379` (service name resolution)

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** https://chatbot-production-2241.up.railway.app
- **Screenshot:** [Service running](screenshots/running.png)

Steps thực hiện:
```bash
npm i -g @railway/cli
railway login
railway link          # link đến project "chatbot"
railway up            # deploy bằng Dockerfile
railway domain        # tạo public URL
```

Health check hoạt động:
```bash
curl https://chatbot-production-2241.up.railway.app/health
# {"status":"ok","version":"1.0.0",...}
```

### Exercise 3.2: railway.toml vs render.yaml

| | railway.toml | render.yaml |
|---|---|---|
| Builder | `DOCKERFILE` | `docker` |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Restart | `restartPolicyType` | `autoDeploy` |
| Env vars | `railway variables set` CLI | Dashboard hoặc `envVars` block |

---

## Part 4: API Security

### Exercise 4.1: API key authentication

- API key được check ở `app/auth.py` — `verify_api_key()` dependency được inject vào mọi protected endpoint
- Nếu sai key → `HTTPException(status_code=401, detail="Invalid API key")`
- Rotate key: thay `AGENT_API_KEY` env var trên Railway, không cần redeploy code

Test:
```bash
# Không có key → 401
curl -X POST https://chatbot-production-2241.up.railway.app/ask \
  -H "Content-Type: application/json" -d '{"question":"hi"}'

# Có key → 200
curl -X POST https://chatbot-production-2241.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","question":"Hello"}'
```

### Exercise 4.2: JWT flow (Advanced)

1. Client gửi `POST /token` với `username` + `password`
2. Server verify credentials → tạo JWT có `exp` (expiry) + `sub` (user_id)
3. JWT được sign bằng `JWT_SECRET` (HMAC-SHA256)
4. Client gửi `Authorization: Bearer <token>` trong mỗi request
5. Server decode và verify signature + expiry

Ưu điểm so với API key: stateless (không cần lookup DB), có expiry tự động, chứa user info

### Exercise 4.3: Rate limiting

- **Algorithm:** Sliding window với Redis Sorted Set (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`)
- **Limit:** 10 requests/minute per `user_id`
- **Bypass cho admin:** Kiểm tra `user_id == "admin"` hoặc dùng whitelist trong config

Khi hit limit → `HTTPException(429, headers={"Retry-After": "60"})`

### Exercise 4.4: Cost guard implementation

```python
def check_budget(user_id: str, estimated_cost: float) -> None:
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    current = float(redis_client.get(key) or 0)
    if current + estimated_cost > settings.monthly_budget_usd:  # $10
        raise HTTPException(status_code=402, detail=f"Monthly budget exceeded. Current: ${current:.4f}")

    redis_client.incrbyfloat(key, estimated_cost)
    redis_client.expire(key, 32 * 24 * 3600)  # 32 ngày
```

Logic: mỗi request estimate cost từ số tokens → cộng dồn vào Redis key theo tháng → nếu vượt $10 thì 402.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    return {"status": "ok"}  # Liveness: process còn sống

@app.get("/ready")
def ready():
    try:
        redis_client.ping()
        return {"ready": True, "redis": "ok"}
    except:
        return JSONResponse(status_code=503, content={"status": "not ready"})
```

- **Liveness (`/health`):** Container còn process không? Nếu fail → restart container
- **Readiness (`/ready`):** Đã kết nối Redis chưa? Nếu fail → không send traffic đến instance này

### Exercise 5.2: Graceful shutdown

```python
import signal

def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))
    # uvicorn timeout_graceful_shutdown=30 đảm bảo finish in-flight requests

signal.signal(signal.SIGTERM, _handle_signal)
```

uvicorn được khởi động với `timeout_graceful_shutdown=30` — khi nhận SIGTERM, sẽ stop accepting new requests và chờ tối đa 30s để finish requests đang chạy.

### Exercise 5.3: Stateless design

**Anti-pattern (in-memory):**
```python
conversation_history = {}  # Mỗi instance có dict riêng → không share được
```

**Correct (Redis):**
```python
def get_history(user_id: str) -> list:
    return redis_client.lrange(f"history:{user_id}", -10, -1)

def append_history(user_id: str, item: dict) -> int:
    key = f"history:{user_id}"
    redis_client.rpush(key, json.dumps(item))
    redis_client.ltrim(key, -20, -1)   # giữ 20 turns gần nhất
    redis_client.expire(key, 7 * 24 * 3600)
    return redis_client.llen(key)
```

Khi scale ra 3 instances, tất cả đều đọc/ghi Redis → conversation history được share.

### Exercise 5.4: Load balancing

```bash
docker compose up --scale agent=3
```

Nginx config (round-robin):
```nginx
upstream agent_pool {
    server agent:8000;  # Docker Compose scale tự tạo nhiều containers
}
```

Quan sát trong logs: request 1 → agent_1, request 2 → agent_2, request 3 → agent_3, rồi lặp lại.

### Exercise 5.5: Test stateless

Script `test_stateless.py`:
1. Tạo conversation với instance 1 (`user_id: "test-user"`)
2. Gửi request với `user_id` đó → get history
3. Kill instance 1 → Docker tự spawn instance mới
4. Gửi tiếp request với cùng `user_id` → history vẫn có trong Redis
5. ✅ Stateless design confirmed

---

## Part 6: Final Project

**Live URL:** https://chatbot-production-2241.up.railway.app

### Architecture implemented

```
Client (Browser UI)
       │
       ▼
FastAPI (Railway, port $PORT)
  ├── GET  /          → Chatbot UI (static HTML)
  ├── GET  /health    → Liveness probe
  ├── GET  /ready     → Readiness probe
  ├── GET  /config    → Demo config (AGENT_API_KEY, limits)
  ├── GET  /metrics   → Metrics (auth required)
  └── POST /ask       → Chat (auth + rate limit + cost guard)
           │
           ├── verify_api_key (auth.py)
           ├── check_rate_limit (rate_limiter.py) — 10 req/min, sliding window
           ├── check_budget (cost_guard.py) — $10/month
           └── llm_ask (utils/mock_llm.py → OpenAI if key set)
                  │
                  └── Redis (history, rate limit, budget)
                        fallback: in-memory dict
```

### Production readiness score

```
20/20 checks passed (100%)
🎉 PRODUCTION READY!
```
