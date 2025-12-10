from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "porto"
    postgres_password: str = "porto_password"
    postgres_db: str = "porto_logistica"
    mongo_url: str = "mongodb://admin:admin123@mongo:27017"
    redis_host: str = "redis"
    redis_port: int = 6379
    decision_engine_url: str = "http://decision-engine:8001"
    environment: str = "development"

settings = Settings()
