"""
Business logic for rentals.

This is the only module allowed to change a car's status as a side
effect of rental activity, so car state and rental state can never drift
apart. Both mutations happen inside a single UnitOfWork — they commit
together or not at all.
"""
from datetime import date

from sqlalchemy.exc import IntegrityError

from app.core.database import UnitOfWork
from app.core.logging_config import get_logger
from app.models.car import CarStatus
from app.models.rental import Rental
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services import events
from app.services.exceptions import (
    CarNotAvailableError,
    CarNotFoundError,
    ConcurrentRentalError,
    RentalAlreadyEndedError,
    RentalNotFoundError,
)

logger = get_logger(__name__)


class RentalService:
    def __init__(self, uow: UnitOfWork, car_repo: CarRepository,
                 rental_repo: RentalRepository, outbox_repo: OutboxRepository):
        self.uow = uow
        self.car_repo = car_repo
        self.rental_repo = rental_repo
        self.outbox_repo = outbox_repo

    def start_rental(self, car_id: int, customer_name: str,
                     start_date: date | None = None) -> Rental:
        try:
            with self.uow:
                # Row lock first: a competing transaction for this same
                # car blocks here until we commit, then reads IN_USE.
                car = self.car_repo.get_for_update(car_id)
                if car is None:
                    raise CarNotFoundError(car_id)

                if car.status != CarStatus.AVAILABLE:
                    logger.warning(
                        "rental.rejected car_id=%s status=%s", car_id, car.status.value
                    )
                    raise CarNotAvailableError(car_id, car.status.value)

                rental = self.rental_repo.create(
                    car_id=car_id,
                    customer_name=customer_name,
                    start_date=start_date or date.today(),
                )
                self.car_repo.apply_changes(car, status=CarStatus.IN_USE)

                # The event is written INSIDE the same transaction. If the
                # commit fails, the event vanishes with the rental — it can
                # never announce something that did not happen. Publishing
                # is the relay's job, not this request's.
                self.outbox_repo.add(events.rental_started(rental))
            # Rental, car status, and event commit atomically.
        except IntegrityError as exc:
            # Backstop: the partial unique index rejected a racing insert
            # that slipped past the status check. Fail loudly, not silently.
            logger.warning("rental.race_lost car_id=%s: %s", car_id, exc.orig)
            raise ConcurrentRentalError(car_id) from exc

        logger.info(
            "rental.started id=%s car_id=%s customer=%s",
            rental.id, car_id, customer_name,
        )
        return rental

    def end_rental(self, rental_id: int, end_date: date | None = None) -> Rental:
        with self.uow:
            rental = self.rental_repo.get_by_id(rental_id)
            if rental is None:
                raise RentalNotFoundError(rental_id)
            if not rental.is_active:
                raise RentalAlreadyEndedError(rental_id)

            rental = self.rental_repo.set_end_date(rental, end_date or date.today())

            # Only free the car if it is still the one out on this rental.
            # A car sent to maintenance mid-rental should stay there.
            car = self.car_repo.get_by_id(rental.car_id)
            if car is not None and car.status == CarStatus.IN_USE:
                self.car_repo.apply_changes(car, status=CarStatus.AVAILABLE)

            self.outbox_repo.add(events.rental_ended(rental))

        logger.info("rental.ended id=%s car_id=%s", rental.id, rental.car_id)
        return rental

    def get_rental(self, rental_id: int) -> Rental:
        rental = self.rental_repo.get_by_id(rental_id)
        if rental is None:
            raise RentalNotFoundError(rental_id)
        return rental

    def list_rentals(self, active_only: bool = False,
                     limit: int = 50, offset: int = 0) -> list[Rental]:
        return self.rental_repo.list_all(
            active_only=active_only, limit=limit, offset=offset
        )
