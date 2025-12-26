"""
Configuration settings for Data Module.
Reads from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "porto"
    postgres_password: str = "porto_password"
    postgres_db: str = "porto_logistica"
    
    # MongoDB
    mongo_url: str = "mongodb://admin:admin123@mongo:27017"
    mongo_host: str = "mongo"
    mongo_port: int = 27017
    
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


settings = Settings()
