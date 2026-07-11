"""Application settings loaded from YAML configuration files and environment variables.

Priority (highest first):
1. Environment variables (e.g. PG_HOST=xxx)
2. YAML configuration file values (config/environments/{ENVIRONMENT}.yaml)
3. Default values defined in the model Fields
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── YAML loading ────────────────────────────────────────────────────────


def _load_yaml_data() -> dict[str, Any]:
    """Load the YAML configuration file for the current environment.

    Returns:
        Dictionary of field_name → value pairs, or empty dict.
    """
    env = os.getenv("ENVIRONMENT", "dev")
    config_dir = Path(__file__).resolve().parent / "environments"
    yaml_path = config_dir / f"{env}.yaml"

    if not yaml_path.exists():
        yaml_path = config_dir / "dev.yaml"

    if not yaml_path.exists():
        return {}

    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Env-var name mapping  (field_name → uppercase env var) ───────────────

_ENV_VAR_MAP: dict[str, str] = {
    "app_name": "APP_NAME",
    "app_version": "APP_VERSION",
    "debug": "DEBUG",
    "environment": "ENVIRONMENT",
    "host": "HOST",
    "port": "PORT",
    "pg_host": "PG_HOST",
    "pg_port": "PG_PORT",
    "pg_user": "PG_USER",
    "pg_password": "PG_PASSWORD",
    "pg_database": "PG_DATABASE",
    "redis_host": "REDIS_HOST",
    "redis_port": "REDIS_PORT",
    "redis_db": "REDIS_DB",
    "redis_password": "REDIS_PASSWORD",
    "qdrant_host": "QDRANT_HOST",
    "qdrant_port": "QDRANT_PORT",
    "qdrant_api_key": "QDRANT_API_KEY",
    "tavily_api_key": "TAVILY_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_base_url": "DEEPSEEK_BASE_URL",
    "deepseek_model": "DEEPSEEK_MODEL",
    "qwen_api_key": "QWEN_API_KEY",
    "qwen_base_url": "QWEN_BASE_URL",
    "qwen_model": "QWEN_MODEL",
    "qwen_light_model": "QWEN_LIGHT_MODEL",
    "qwen_medium_model": "QWEN_MEDIUM_MODEL",
    "mcp_search_url": "MCP_SEARCH_URL",
    "mcp_database_url": "MCP_DATABASE_URL",
    "mcp_chart_url": "MCP_CHART_URL",
    "mcp_email_url": "MCP_EMAIL_URL",
    "cb_failure_threshold": "CB_FAILURE_THRESHOLD",
    "cb_timeout": "CB_TIMEOUT",
    "rate_limit_requests": "RATE_LIMIT_REQUESTS",
    "rate_limit_window": "RATE_LIMIT_WINDOW",
    "jwt_secret_key": "JWT_SECRET_KEY",
    "api_key_header": "API_KEY_HEADER",
    "embedding_model": "EMBEDDING_MODEL",
    "reranker_enabled": "RERANKER_ENABLED",
    "reranker_model": "RERANKER_MODEL",
    "log_level": "LOG_LEVEL",
    "langsmith_api_key": "LANGSMITH_API_KEY",
    "langsmith_project": "LANGSMITH_PROJECT",
}


def _collect_env_overrides() -> dict[str, Any]:
    """Collect overrides from matching environment variables.

    For every field listed in _ENV_VAR_MAP, if the corresponding
    uppercase env var is set, return its value keyed by field_name.
    """
    overrides: dict[str, Any] = {}
    for field_name, env_var in _ENV_VAR_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            # Coerce booleans for the 'debug' field
            if field_name == "debug":
                overrides[field_name] = val.lower() in ("1", "true", "yes")
            elif field_name in (
                "port", "pg_port", "redis_port", "qdrant_port",
                "redis_db", "cb_failure_threshold", "cb_timeout",
                "rate_limit_requests", "rate_limit_window",
            ):
                overrides[field_name] = int(val)
            else:
                overrides[field_name] = val
    return overrides


# ── Settings model ──────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Unified application settings.

    Construct with ``Settings()`` to load from YAML + env vars automatically.
    The module-level ``settings`` singleton is also available for convenience.

    Priority (highest first):
    1. Environment variables (e.g. PG_HOST=xxx)
    2. YAML configuration file values
    3. Default values defined in the model Fields
    """

    model_config = SettingsConfigDict(extra="ignore")

    def __init__(self, **kwargs: Any) -> None:
        yaml_data = _load_yaml_data()
        env_overrides = _collect_env_overrides()
        yaml_data.update(env_overrides)
        yaml_data.update(kwargs)
        super().__init__(**yaml_data)

    # ── App ──────────────────────────────────────────────────────────
    app_name: str = Field(default="智能研报生成系统")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    environment: str = Field(default="dev")

    # ── Server ───────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # ── PostgreSQL ───────────────────────────────────────────────────
    pg_host: str = Field(default="localhost")
    pg_port: int = Field(default=5432)
    pg_user: str = Field(default="postgres")
    pg_password: str = Field(default="postgres")
    pg_database: str = Field(default="research_agent")

    @property
    def pg_dsn(self) -> str:
        """Build the async PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def pg_dsn_sync(self) -> str:
        """Build the synchronous PostgreSQL connection string."""
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    # ── Redis ────────────────────────────────────────────────────────
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: Optional[str] = Field(default=None)

    @property
    def redis_url(self) -> str:
        """Build the Redis connection URL."""
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}"
                f"@{self.redis_host}:{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── Qdrant ───────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_api_key: Optional[str] = Field(default=None)

    # ── Tavily ────────────────────────────────────────────────────────
    tavily_api_key: str = Field(default="")

    # ── DeepSeek ─────────────────────────────────────────────────────
    deepseek_api_key: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-v3")

    # ── Qwen ─────────────────────────────────────────────────────────
    qwen_api_key: str = Field(default="")
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    qwen_model: str = Field(default="qwen-max")
    qwen_light_model: str = Field(default="qwen3-1.8b")
    qwen_medium_model: str = Field(default="qwen3-7b")

    # ── MCP ──────────────────────────────────────────────────────────
    mcp_search_url: str = Field(default="http://localhost:8001")
    mcp_database_url: str = Field(default="http://localhost:8002")
    mcp_chart_url: str = Field(default="http://localhost:8003")
    mcp_email_url: str = Field(default="http://localhost:8004")

    # ── Circuit Breaker ──────────────────────────────────────────────
    cb_failure_threshold: int = Field(default=3)
    cb_timeout: int = Field(default=30)

    # ── Rate Limit ───────────────────────────────────────────────────
    rate_limit_requests: int = Field(default=60)
    rate_limit_window: int = Field(default=60)

    # ── Security ─────────────────────────────────────────────────────
    jwt_secret_key: str = Field(default="change-me-in-production")
    api_key_header: str = Field(default="X-API-Key")

    # ── Embedding ────────────────────────────────────────────────────
    embedding_model: str = Field(default="bge-m3")

    # ── Reranker ──────────────────────────────────────────────────────
    reranker_enabled: bool = Field(default=False)
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")

    # ── Logging ──────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")

    # ── LangSmith (optional) ─────────────────────────────────────────
    langsmith_api_key: Optional[str] = Field(default=None)
    langsmith_project: Optional[str] = Field(default=None)


# Singleton instance — import this throughout the application
settings = Settings()
