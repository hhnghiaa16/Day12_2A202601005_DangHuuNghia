# ============================================================
# Production Dockerfile — Multi-stage, minimal, Railway-ready
# ============================================================

# Stage 1: Builder — install dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Runtime — lean final image
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN useradd -r -m -u 1001 agent

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/agent/.local

# Copy application code
COPY app/ ./app/
COPY utils/ ./utils/

RUN chown -R agent:agent /app /home/agent

USER agent

ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/health')" || exit 1

CMD ["python", "-m", "app.serve"]
