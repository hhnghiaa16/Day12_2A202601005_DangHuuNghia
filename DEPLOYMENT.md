# Deployment Information

> **Student:** Đặng Hữu Nghĩa — 2A202601005  
> **Date:** 2026-06-12

---

## Public URL

```
https://chatbot-production-2241.up.railway.app
```

## Platform

**Railway** — Dockerfile build, single-service deployment

---

## Test Commands

### Health Check

```bash
curl https://chatbot-production-2241.up.railway.app/health
```

Expected response:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 123.4,
  "total_requests": 5,
  "storage": "memory",
  "timestamp": "2026-06-12T10:09:00Z"
}
```

### Readiness Check

```bash
curl https://chatbot-production-2241.up.railway.app/ready
```

### API Test — No Auth (should return 401)

```bash
curl -X POST https://chatbot-production-2241.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401 Missing API key
```

### API Test — With Auth

```bash
curl -X POST https://chatbot-production-2241.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello from cloud"}'
```

### Rate Limit Test (429 after 10 requests)

```bash
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://chatbot-production-2241.up.railway.app/ask \
    -H "X-API-Key: dev-key-change-me" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"ratelimit-test\",\"question\":\"Test $i\"}"
done
# Expected: 200 x10 then 429
```

---

## Environment Variables Set on Railway

| Variable | Description |
|---|---|
| `PORT` | Auto-set by Railway |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Chatbot access key |
| `OPENAI_API_KEY` | OpenAI API key (server-side only, never exposed) |
| `LLM_MODEL` | `gpt-4o-mini` |

---

## Screenshots

- [Service running](screenshots/running.png)
- [Deployment dashboard](screenshots/dashboard.png)
- [Test results](screenshots/test.png)

---

## Production Readiness Score

```
20/20 checks passed (100%) — python check_production_ready.py
```

All items ✅:
- Dockerfile (multi-stage, slim base)
- Non-root user
- HEALTHCHECK instruction
- .dockerignore
- .env.example
- railway.toml
- /health endpoint
- /ready endpoint
- API key authentication
- Rate limiting (10 req/min)
- Cost guard ($10/month)
- Graceful shutdown (SIGTERM)
- Structured JSON logging
- No hardcoded secrets
- Stateless design (Redis fallback to memory)
