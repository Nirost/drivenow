"""
Integration tests against real PostgreSQL.

These close the coverage gap the SQLite suite cannot reach: SQLite ignores
SELECT ... FOR UPDATE, so the row-locking path that serializes concurrent
rental attempts is only genuinely exercised here.

Skipped automatically unless DATABASE_URL points at PostgreSQL:
    DATABASE_URL=postgresql+psycopg2://... uv run pytest -m integration
"""
import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, UnitOfWork
from app.models.car import Car, CarStatus
from app.models.outbox import OutboxEvent
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services.exceptions import CarNotAvailableError, ConcurrentRentalError
from app.services.rental_service import RentalService

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv("DATABASE_URL", "")

pytest.importorskip("psycopg2")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip(
        "PostgreSQL integration tests require a postgresql DATABASE_URL",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def clean_db(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE outbox_events, processed_events, rentals, cars "
                          "RESTART IDENTITY CASCADE"))
    return pg_engine


def _make_service(engine):
    session = sessionmaker(bind=engine, future=True)()
    return session, RentalService(
        UnitOfWork(session),
        CarRepository(session),
        RentalRepository(session),
        OutboxRepository(session),
    )


def test_concurrent_rentals_yield_exactly_one_winner(clean_db):
    """
    The test SQLite cannot run.

    Two threads race to rent the same car through independent database
    connections. Exactly one must win; the other must be rejected cleanly
    rather than producing a second active rental.
    """
    engine = clean_db
    setup_session, _ = _make_service(engine)
    car = Car(model="Contended", year=2023, status=CarStatus.AVAILABLE)
    setup_session.add(car)
    setup_session.commit()
    car_id = car.id
    setup_session.close()

    results: list[str] = []
    barrier = threading.Barrier(2)
    lock = threading.Lock()

    def attempt(customer: str):
        session, service = _make_service(engine)
        try:
            barrier.wait(timeout=10)  # maximize overlap
            service.start_rental(car_id=car_id, customer_name=customer)
            outcome = "won"
        except (CarNotAvailableError, ConcurrentRentalError):
            outcome = "rejected"
        except Exception as exc:  # pragma: no cover - diagnostic
            outcome = f"error:{type(exc).__name__}"
        finally:
            session.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(f"Racer {i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert sorted(results) == ["rejected", "won"], results

    verify = sessionmaker(bind=engine, future=True)()
    try:
        active = verify.execute(
            text("SELECT COUNT(*) FROM rentals WHERE end_date IS NULL")
        ).scalar()
        status = verify.execute(
            text("SELECT status FROM cars WHERE id = :i"), {"i": car_id}
        ).scalar()
        events = verify.query(OutboxEvent).filter(
            OutboxEvent.event_type == "rental.started"
        ).count()
    finally:
        verify.close()

    assert active == 1, "exactly one rental may be active"
    assert status == "IN_USE"
    assert events == 1, "the losing transaction must not have left an event"


def test_partial_unique_index_exists(clean_db):
    """Guards against the index being dropped from a future migration."""
    with clean_db.connect() as conn:
        found = conn.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uq_one_active_rental_per_car'"
        )).scalar()
    assert found is not None
    assert "end_date IS NULL" in found


def test_jsonb_payload_is_queryable(clean_db):
    """The outbox payload is JSONB on PostgreSQL, so it can be filtered."""
    session, service = _make_service(clean_db)
    try:
        car = Car(model="Queryable", year=2022, status=CarStatus.AVAILABLE)
        session.add(car)
        session.commit()
        service.start_rental(car_id=car.id, customer_name="Jsonb Jane")

        found = session.execute(text(
            "SELECT payload->>'customer_name' FROM outbox_events "
            "WHERE event_type = 'rental.started'"
        )).scalar()
    finally:
        session.close()

    assert found == "Jsonb Jane"
