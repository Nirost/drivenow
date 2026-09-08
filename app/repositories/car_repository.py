"""
Data access layer for Car.

Repositories are the only code that speaks SQLAlchemy. They `flush()`
but never `commit()` — see app/core/database.UnitOfWork for why.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.car import Car, CarStatus


class CarRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self, include_deleted: bool = False):
        stmt = select(Car)
        if not include_deleted:
            stmt = stmt.where(Car.deleted_at.is_(None))
        return stmt

    def create(self, model: str, year: int, status: CarStatus = CarStatus.AVAILABLE) -> Car:
        car = Car(model=model, year=year, status=status)
        self.db.add(car)
        self.db.flush()  # assigns car.id without ending the transaction
        return car

    def get_by_id(self, car_id: int, include_deleted: bool = False) -> Car | None:
        stmt = self._base_query(include_deleted).where(Car.id == car_id)
        return self.db.scalars(stmt).first()

    def get_for_update(self, car_id: int) -> Car | None:
        """
        Fetch a car with a row-level lock (SELECT ... FOR UPDATE).

        Serializes concurrent rental attempts on the same vehicle: the
        second transaction blocks here until the first commits, then sees
        status=IN_USE and is rejected cleanly.

        Note: SQLite ignores FOR UPDATE (it locks the whole database
        instead), so this is a no-op under the test suite. Correctness on
        SQLite still holds via the partial unique index on rentals.
        """
        stmt = select(Car).where(Car.id == car_id, Car.deleted_at.is_(None)).with_for_update()
        return self.db.scalars(stmt).first()

    def list_all(
        self, status: CarStatus | None = None, limit: int = 50, offset: int = 0
    ) -> list[Car]:
        stmt = self._base_query()
        if status is not None:
            stmt = stmt.where(Car.status == status)
        stmt = stmt.order_by(Car.id).limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def count(self, status: CarStatus | None = None) -> int:
        """COUNT in the database — never load rows just to len() them."""
        stmt = select(func.count()).select_from(Car).where(Car.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Car.status == status)
        return self.db.scalar(stmt) or 0

    def apply_changes(self, car: Car, **fields) -> Car:
        """
        Apply already-validated field changes. The caller decides which
        fields are present; this method does not silently drop None.
        """
        for key, value in fields.items():
            setattr(car, key, value)
        self.db.flush()
        return car

    def soft_delete(self, car: Car) -> Car:
        car.deleted_at = datetime.now(UTC)
        self.db.flush()
        return car
