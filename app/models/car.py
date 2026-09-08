import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    # Import only for type checking: at runtime SQLAlchemy resolves the
    # relationship by name, and a real import would be circular.
    from app.models.rental import Rental


class CarStatus(str, enum.Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    UNDER_MAINTENANCE = "under_maintenance"


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CarStatus] = mapped_column(
        Enum(CarStatus, native_enum=False, length=32),
        nullable=False,
        default=CarStatus.AVAILABLE,
    )

    # Soft delete. A rental company must not lose the vehicle record that
    # historical rentals (and invoices) point at, so "delete" retires the
    # car instead of removing the row.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # No delete-orphan cascade: rentals are financial history and must
    # outlive the vehicle record.
    rentals: Mapped[list["Rental"]] = relationship(back_populates="car")

    __table_args__ = (
        # status is the primary filter for GET /cars; deleted_at is in
        # every query's WHERE clause.
        Index("ix_cars_status", "status"),
        Index("ix_cars_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<Car id={self.id} model={self.model!r} status={self.status.value}>"
