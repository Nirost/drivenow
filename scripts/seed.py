"""
Populate the database with demo data.

Useful for screenshots and for exercising the event pipeline end to end:
run this with the stack up and watch events flow through the relay into
the notifications consumer.

    make seed
"""
from datetime import date, timedelta

from app.core.database import SessionLocal, UnitOfWork
from app.core.logging_config import setup_logging
from app.models.car import CarStatus
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services.car_service import CarService
from app.services.rental_service import RentalService

FLEET = [
    ("Tesla Model 3", 2023),
    ("Toyota Corolla", 2022),
    ("Volkswagen Golf", 2021),
    ("Ford Focus", 2020),
    ("Mazda CX-5", 2023),
    ("Renault Clio", 2019),
]


def main() -> None:
    setup_logging()
    session = SessionLocal()
    try:
        uow = UnitOfWork(session)
        car_repo = CarRepository(session)
        rental_repo = RentalRepository(session)
        outbox_repo = OutboxRepository(session)

        cars_service = CarService(uow, car_repo, rental_repo, outbox_repo)
        rentals_service = RentalService(uow, car_repo, rental_repo, outbox_repo)

        cars = [cars_service.add_car(model=m, year=y) for m, y in FLEET]

        # One completed rental (history), one ongoing, one car in maintenance.
        past = rentals_service.start_rental(
            car_id=cars[0].id,
            customer_name="Maya Cohen",
            start_date=date.today() - timedelta(days=7),
        )
        rentals_service.end_rental(past.id, end_date=date.today() - timedelta(days=2))

        rentals_service.start_rental(
            car_id=cars[1].id,
            customer_name="Daniel Levi",
            start_date=date.today() - timedelta(days=1),
        )

        cars_service.update_car(cars[3].id, status=CarStatus.UNDER_MAINTENANCE)

        print(f"Seeded {len(cars)} cars, 2 rentals (1 ongoing), 1 in maintenance.")
        print("Events are queued in the outbox — the relay will publish them.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
