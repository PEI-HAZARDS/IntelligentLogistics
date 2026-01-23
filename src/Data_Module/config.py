"""
Configuration settings for Data Module.
Reads from environment variables with sensible defaults.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = os.getenv("POSTGRES_USER", "porto")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_db: str = "porto_logistica"
    
    # MongoDB
    mongo_initdb_root_username: str = "admin"
    mongo_initdb_root_password: str = ""
    mongo_host: str = "mongo"
    mongo_port: int = 27017
    
    @property
    def mongo_url(self) -> str:
        """Construct MongoDB URL from environment variables."""
        return f"mongodb://{self.mongo_initdb_root_username}:{self.mongo_initdb_root_password}@{self.mongo_host}:{self.mongo_port}"
    
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    
    # External services
    decision_engine_url: str = "http://decision-engine:8001"
    
    # Runtime
    environment: str = "development"
    debug: bool = False
    
    # Driver Authentication
    debug_mode: bool = False  # When True, allows bypassing sequential delivery checks
    token_expiry_hours: int = 24  # Session token expiration time in hours
    
    # API
    api_prefix: str = "/api/v1"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
