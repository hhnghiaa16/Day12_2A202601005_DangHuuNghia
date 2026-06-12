"""12-factor configuration loaded from environment variables."""
import logging
import os
from dataclasses import dataclass, field


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning("%s is invalid; using %s", name, default)
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning("%s is invalid; using %s", name, default)
        return default


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production Chatbot"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-jwt-secret"))
    allowed_origins: list[str] = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(","))

    rate_limit_per_minute: int = field(default_factory=lambda: env_int("RATE_LIMIT_PER_MINUTE", 10))
    monthly_budget_usd: float = field(default_factory=lambda: env_float("MONTHLY_BUDGET_USD", 10.0))
    input_cost_per_1k: float = field(default_factory=lambda: env_float("INPUT_COST_PER_1K", 0.00015))
    output_cost_per_1k: float = field(default_factory=lambda: env_float("OUTPUT_COST_PER_1K", 0.0006))

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))

    def validate(self):
        logger = logging.getLogger(__name__)
        if self.environment == "production" and self.agent_api_key == "dev-key-change-me":
            logger.warning("AGENT_API_KEY is using the demo default; set a real value before submission")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not set; using mock LLM")
        if not self.redis_url:
            logger.warning("REDIS_URL not set; using in-memory fallback storage")
        return self


settings = Settings().validate()
