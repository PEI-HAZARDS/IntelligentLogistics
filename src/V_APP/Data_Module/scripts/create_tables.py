#!/usr/bin/env python3
"""
Creates all PostgreSQL tables from SQLAlchemy models.
Must run BEFORE triggers.sql and data_init so that:
  1. Tables exist when triggers.sql attaches triggers
  2. Triggers fire on INSERT during data_init seeding
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from infrastructure.persistence.sql_models import Base
import infrastructure.persistence.inbox_outbox_models  # noqa: F401 — registers InboxEvent/OutboxEvent in Base.metadata

if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    print("Tables created successfully.")
