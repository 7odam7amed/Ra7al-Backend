import pytest
from sqlalchemy import text

from app.core.database import SessionLocal, engine


def test_database_engine_connects(db_available: bool) -> None:
    if not db_available:
        pytest.skip("PostgreSQL is not available; start it with docker compose up db")

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


def test_database_session_works(db_available: bool) -> None:
    if not db_available:
        pytest.skip("PostgreSQL is not available; start it with docker compose up db")

    db = SessionLocal()
    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    finally:
        db.close()
