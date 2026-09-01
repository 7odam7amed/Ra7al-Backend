from collections.abc import Generator
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.database import Base, SessionLocal, get_db
from app.core.rate_limiter import limiter_store
from app.main import app
from app.models import (  # noqa: F401

    BaseModel,
    Bus,
    BusStatus,
    GenderEnum,
    Payment,
    PaymentMethod,
    PaymentStatus,
    PickupPoint,
    Reservation,
    ReservationStatus,
    RoleEnum,
    Route,
    RouteStop,
    Station,
    Trip,
    TripStatus,
    University,
    User,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def db_available() -> bool:
    """Check whether PostgreSQL is reachable for integration tests."""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except SQLAlchemyError:
        return False


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client_with_db(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient wired to the isolated testing database."""
    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    from app.api import deps
    deps._shared_whatsapp_service = None
    get_settings.cache_clear()
    limiter_store.reset()
    yield
    deps._shared_whatsapp_service = None
    get_settings.cache_clear()
    limiter_store.reset()

