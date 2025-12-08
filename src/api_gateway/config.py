from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configurações do API Gateway.

    Todas estas variáveis podem ser sobrepostas por variáveis
    de ambiente ou por um ficheiro .env na raiz do serviço.
    """

    # URL base do Data Module (Internal API)
    # Em Docker (rede interna):
    #   http://data-module:8080
    # Em ambiente remoto, deve ser sobreposto por variável de ambiente:
    #   DATA_MODULE_URL=http://backend.example.com:8080
    DATA_MODULE_URL: str = "http://data-module:8080"

    # URL base do servidor de streams (Nginx-RTMP com HLS)
    # Em Docker:
    #   http://nginx-rtmp:8080
    # Em ambiente remoto, deve ser sobreposto por variável de ambiente:
    #   STREAM_BASE_URL=http://stream.example.com:8080
    STREAM_BASE_URL: str = "http://nginx-rtmp:8080"

    # Prefixo base da API exposta pelo gateway (ex: /api)
    API_PREFIX: str = "/api"

    # Ambiente (só para futuro uso/logging)
    ENV: str = "dev"

    # CORS – por agora deixamos aberto; podes apertar depois
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
