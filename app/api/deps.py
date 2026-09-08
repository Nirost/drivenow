"""FastAPI dependency wiring: session -> UoW -> repositories -> services."""
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import UnitOfWork, get_db
from app.repositories.car_repository import CarRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.rental_repository import RentalRepository
from app.services.car_service import CarService
from app.services.rental_service import RentalService

DbSession = Annotated[Session, Depends(get_db)]


def get_uow(db: DbSession) -> UnitOfWork:
    return UnitOfWork(db)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_car_service(db: DbSession, uow: UowDep) -> CarService:
    return CarService(
        uow, CarRepository(db), RentalRepository(db), OutboxRepository(db)
    )


def get_rental_service(db: DbSession, uow: UowDep) -> RentalService:
    return RentalService(
        uow, CarRepository(db), RentalRepository(db), OutboxRepository(db)
    )


CarServiceDep = Annotated[CarService, Depends(get_car_service)]
RentalServiceDep = Annotated[RentalService, Depends(get_rental_service)]


class Pagination:
    """Shared, bounded pagination — max_page_size prevents `?limit=999999`."""

    def __init__(
        self,
        limit: int = Query(default=settings.default_page_size, ge=1,
                           le=settings.max_page_size),
        offset: int = Query(default=0, ge=0),
    ):
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
