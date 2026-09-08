"""Operational endpoints: liveness, readiness, and metrics."""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.core.metrics import (
    active_cars_gauge,
    fleet_size_gauge,
    ongoing_rentals_gauge,
    outbox_failed_gauge,
    outbox_pending_gauge,
)
from app.models.car import CarStatus
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository

router = APIRouter(tags=["system"])


@router.get("/health/live")
def liveness():
    """Is the process up? Used by the container restart policy."""
    return {"status": "ok", "environment": settings.environment}


@router.get("/health/ready")
def readiness(db: DbSession, response: Response):
    """
    Can we actually serve traffic? Checks the database round-trip.
    A liveness probe that ignores the DB will happily report healthy
    while every request 500s.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "unavailable", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}


@router.get("/metrics")
def metrics(db: DbSession):
    car_repo = CarRepository(db)
    # COUNT(*) in the database, not len() over hydrated ORM objects.
    active_cars_gauge.set(car_repo.count(status=CarStatus.AVAILABLE))
    fleet_size_gauge.set(car_repo.count())
    ongoing_rentals_gauge.set(RentalRepository(db).count_active())

    # Outbox depth is the key health signal for the async path: a rising
    # pending count means the relay is down or the broker is unreachable.
    outbox_repo = OutboxRepository(db)
    outbox_pending_gauge.set(outbox_repo.count_pending())
    outbox_failed_gauge.set(outbox_repo.count_failed())

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
