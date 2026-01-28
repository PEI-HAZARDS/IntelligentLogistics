from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configurações do API Gateway.

    Todas estas variáveis podem ser sobrepostas por variáveis
    de ambiente ou por um ficheiro .env na raiz do serviço.
    """

    # URL base do Data Module (Internal API)
    DATA_MODULE_URL: str = "http://data-module:8080"

    # URL base do servidor de streams (Nginx-RTMP com HLS)
    STREAM_BASE_URL: str = "http://nginx-rtmp:8080"

    # Kafka – para consumir decisões em tempo real
    # Em Docker (nome do serviço Kafka):
    #   kafka:9092
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"

    # Tópico REAL com os resultados das decisões
    KAFKA_DECISION_TOPIC: str = "decision_results"

    # (Opcional) consumer group do gateway – se tiveres várias instâncias
    KAFKA_CONSUMER_GROUP: str = "api-gateway-decisions"

    # Prefixo base da API exposta pelo gateway (ex: /api)
    API_PREFIX: str = "/api"

    # Ambiente
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
