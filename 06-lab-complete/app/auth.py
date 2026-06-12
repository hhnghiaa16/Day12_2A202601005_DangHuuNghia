"""API key authentication dependency."""
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
