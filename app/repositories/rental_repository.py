"""Data access layer for Rental. Flushes, never commits."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.rental import Rental


class RentalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, car_id: int, customer_name: str, start_date: date) -> Rental:
        rental = Rental(car_id=car_id, customer_name=customer_name, start_date=start_date)
        self.db.add(rental)
        self.db.flush()
        return rental

    def get_by_id(self, rental_id: int) -> Rental | None:
        return self.db.get(Rental, rental_id)

    def get_for_update(self, rental_id: int) -> Rental | None:
        """
        Fetch a rental with a row-level lock, serializing concurrent
        attempts to end the same rental.
        """
        stmt = select(Rental).where(Rental.id == rental_id).with_for_update()
        return self.db.scalars(stmt).first()

    def get_active_for_car(self, car_id: int) -> Rental | None:
        stmt = select(Rental).where(Rental.car_id == car_id, Rental.end_date.is_(None))
        return self.db.scalars(stmt).first()

    def list_all(self, active_only: bool = False, limit: int = 50, offset: int = 0) -> list[Rental]:
        stmt = select(Rental).options(joinedload(Rental.car))
        if active_only:
            stmt = stmt.where(Rental.end_date.is_(None))
        stmt = stmt.order_by(Rental.id).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def set_end_date(self, rental: Rental, end_date: date) -> Rental:
        rental.end_date = end_date
        self.db.flush()
        return rental

    def count_active(self) -> int:
        stmt = select(func.count()).select_from(Rental).where(Rental.end_date.is_(None))
        return self.db.scalar(stmt) or 0
