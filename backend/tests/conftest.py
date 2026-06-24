import pytest
from typing import Generator
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, sync_engine

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initializes schema on the test database."""
    Base.metadata.create_all(bind=sync_engine)
    yield
    # Keep database tables after tests so dev server / fuzzer can use them.
    # Base.metadata.drop_all(bind=sync_engine)

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides an isolated database session per test case."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
