from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from models.sql_models import Base

DATABASE_URL = (
    f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Apenas para desenvolvimento — NUNCA EM PRODUÇÃO
if settings.environment == "development":
    Base.metadata.create_all(bind=engine)
