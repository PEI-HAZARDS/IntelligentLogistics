"""
Configuration settings for Data Module.
Reads from environment variables with sensible defaults.
"""

import logging
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_JWT_SECRET = "pei-internal-secret-replace-with-keycloak"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL — pydantic-settings reads POSTGRES_USER / POSTGRES_PASSWORD from env
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "porto"
    postgres_password: str = ""
    postgres_db: str = "porto_logistica"

    # MongoDB
    mongo_initdb_root_username: str = "admin"
    mongo_initdb_root_password: str = ""
    mongo_host: str = "mongo"
    mongo_port: int = 27017

    @property
    def mongo_url(self) -> str:
        return (
            f"mongodb://{self.mongo_initdb_root_username}:"
            f"{self.mongo_initdb_root_password}@{self.mongo_host}:{self.mongo_port}"
        )

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # External services
    decision_engine_url: str = "http://decision-engine:8001"
    # Service-to-service key for Decision Engine → Data Module calls.
    # Set DECISION_ENGINE_KEY in env to enforce; empty string disables the check.
    decision_engine_key: str = ""

    # Runtime
    environment: str = "development"
    debug: bool = False

    # Kafka
    kafka_bootstrap: str = "kafka:29092"
    gate_id: str = "1"

    # Authentication
    jwt_secret: str = _DEFAULT_JWT_SECRET
    debug_mode: bool = False
    token_expiry_hours: int = 24
    # When True, auth continues via JWT-only if Redis is unavailable (fail-open).
    # Set REDIS_AUTH_FAIL_OPEN=false in production to fail closed (return 503).
    redis_auth_fail_open: bool = True

    # CORS — set CORS_ORIGINS env var as JSON array or comma-separated string
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # API
    api_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

if settings.jwt_secret == _DEFAULT_JWT_SECRET and settings.environment != "development":
    raise ValueError(
        "JWT_SECRET is set to the insecure default. "
        "Set the JWT_SECRET environment variable before starting in non-development mode."
    )
