"""Entrypoint for Docker / Railway — runs uvicorn directly."""
import os
import logging
import uvicorn


def safe_port() -> int:
    try:
        return int(os.getenv("PORT", "8000"))
    except (TypeError, ValueError):
        logging.warning("Invalid PORT=%r; using 8000", os.getenv("PORT"))
        return 8000


uvicorn.run(
    "app.main:app",
    host=os.getenv("HOST", "0.0.0.0"),
    port=safe_port(),
    timeout_graceful_shutdown=30,
)
