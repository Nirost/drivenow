from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Import only for type checking: at runtime SQLAlchemy resolves the
    # relationship by name, and a real import would be circular.
    from app.models.car import Car


class Rental(Base):
    __tablename__ = "rentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(
        # RESTRICT, not CASCADE: the database refuses to drop a car that
        # has rental history. Retiring a car is a soft delete instead.
        ForeignKey("cars.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    # NULL means the rental is still ongoing. This is what the partial
    # unique index below keys on.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    car: Mapped["Car"] = relationship(back_populates="rentals")

    __table_args__ = (
        # THE double-booking guard. Application-level checks lose races;
        # this makes "two ongoing rentals for one car" unrepresentable in
        # the database, so a lost race fails loudly with IntegrityError
        # instead of silently corrupting the fleet state.
        Index(
            "uq_one_active_rental_per_car",
            "car_id",
            unique=True,
            postgresql_where=text("end_date IS NULL"),
            sqlite_where=text("end_date IS NULL"),
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_rentals_end_after_start",
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.end_date is None

    def __repr__(self) -> str:
        return f"<Rental id={self.id} car_id={self.car_id} active={self.is_active}>"
