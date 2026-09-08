"""Business logic for vehicle management."""
from app.core.database import UnitOfWork
from app.core.logging_config import get_logger
from app.models.car import Car, CarStatus
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services import events
from app.services.exceptions import (
    CarHasActiveRentalError,
    CarNotFoundError,
    NoFieldsToUpdateError,
)

logger = get_logger(__name__)

# Fields a client is permitted to modify. Anything else is rejected rather
# than silently ignored, so a typo'd field name is a loud error.
UPDATABLE_FIELDS = frozenset({"model", "year", "status"})


class CarService:
    def __init__(self, uow: UnitOfWork, car_repo: CarRepository,
                 rental_repo: RentalRepository, outbox_repo: OutboxRepository):
        self.uow = uow
        self.car_repo = car_repo
        self.rental_repo = rental_repo
        self.outbox_repo = outbox_repo

    def add_car(self, model: str, year: int) -> Car:
        with self.uow:
            car = self.car_repo.create(model=model, year=year)
            self.outbox_repo.add(events.car_added(car))
        logger.info("car.added id=%s model=%s year=%s", car.id, car.model, car.year)
        return car

    def get_car(self, car_id: int) -> Car:
        car = self.car_repo.get_by_id(car_id)
        if car is None:
            raise CarNotFoundError(car_id)
        return car

    def list_cars(self, status: CarStatus | None = None,
                  limit: int = 50, offset: int = 0) -> list[Car]:
        return self.car_repo.list_all(status=status, limit=limit, offset=offset)

    def update_car(self, car_id: int, **changes) -> Car:
        """
        Partial update.

        The caller passes only the fields it actually wants changed — the
        API layer derives that from Pydantic's `exclude_unset`, so
        "field omitted" and "field set to null" stay distinguishable
        instead of both collapsing to None.
        """
        unknown = set(changes) - UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown updatable field(s): {sorted(unknown)}")
        if not changes:
            raise NoFieldsToUpdateError()

        car = self.get_car(car_id)
        with self.uow:
            car = self.car_repo.apply_changes(car, **changes)

        logger.info("car.updated id=%s changes=%s", car_id, sorted(changes))
        return car

    def retire_car(self, car_id: int) -> None:
        """
        Soft delete. Rental history references this row, so it is retired
        rather than removed; the FK is RESTRICT so the database would
        reject a hard delete anyway.
        """
        car = self.get_car(car_id)

        active = self.rental_repo.get_active_for_car(car_id)
        if active is not None:
            logger.warning("car.retire_rejected id=%s active_rental=%s", car_id, active.id)
            raise CarHasActiveRentalError(car_id, active.id)

        with self.uow:
            self.car_repo.soft_delete(car)
            self.outbox_repo.add(events.car_retired(car))

        logger.info("car.retired id=%s", car_id)
