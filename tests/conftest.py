import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, UnitOfWork
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services.car_service import CarService
from app.services.rental_service import RentalService


@pytest.fixture()
def engine():
    """
    In-memory SQLite, shared across connections via StaticPool so the
    schema created here is visible to the app's sessions.

    SQLite ignores SELECT ... FOR UPDATE, so the locking path is not
    exercised here — but the partial unique index IS enforced by SQLite,
    so the double-booking guard is genuinely covered.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce foreign keys unless asked.
    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def uow(db_session):
    return UnitOfWork(db_session)


@pytest.fixture()
def outbox_repo(db_session):
    return OutboxRepository(db_session)


@pytest.fixture()
def car_service(uow, db_session, outbox_repo):
    return CarService(
        uow, CarRepository(db_session), RentalRepository(db_session), outbox_repo
    )


@pytest.fixture()
def rental_service(uow, db_session, outbox_repo):
    return RentalService(
        uow, CarRepository(db_session), RentalRepository(db_session), outbox_repo
    )


@pytest.fixture()
def publisher():
    from app.messaging.publisher import InMemoryPublisher

    return InMemoryPublisher()


@pytest.fixture()
def relay(publisher):
    from app.relay.relay import OutboxRelay

    return OutboxRelay(publisher, batch_size=10, poll_interval=0, max_attempts=3)


@pytest.fixture()
def client(engine):
    """API test client backed by the same in-memory database."""
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
