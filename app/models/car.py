import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, Integer, String, func, text
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
        # One index for the only shape these queries take: every car read
        # filters `deleted_at IS NULL`, optionally narrows by status, and
        # orders by id. Restricting it to live cars keeps retired rows out
        # entirely, and the trailing id satisfies the ORDER BY without a
        # sort. Two separate low-selectivity indexes on status and
        # deleted_at matched no query the application actually issues.
        Index(
            "ix_cars_live_status",
            "status",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Car id={self.id} model={self.model!r} status={self.status.value}>"
