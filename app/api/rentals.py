"""Rental endpoints. Error translation lives in app/api/errors.py."""

from fastapi import APIRouter, Query, status

from app.api.deps import PaginationDep, RentalServiceDep
from app.api.schemas import ErrorResponse, RentalCreate, RentalEnd, RentalOut

router = APIRouter(prefix="/rentals", tags=["rentals"])

_ERRORS = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}


@router.post("", response_model=RentalOut, status_code=status.HTTP_201_CREATED, responses=_ERRORS)
def start_rental(payload: RentalCreate, service: RentalServiceDep):
    """
    Register a rental and mark the vehicle in use.

    409 if the car is not available, or if a concurrent request won the
    race for the same vehicle.
    """
    return service.start_rental(
        car_id=payload.car_id,
        customer_name=payload.customer_name,
        start_date=payload.start_date,
    )


@router.get("", response_model=list[RentalOut])
def list_rentals(
    service: RentalServiceDep,
    page: PaginationDep,
    active_only: bool = Query(default=False, description="Only ongoing rentals"),
):
    return service.list_rentals(active_only=active_only, limit=page.limit, offset=page.offset)


@router.get("/{rental_id}", response_model=RentalOut, responses=_ERRORS)
def get_rental(rental_id: int, service: RentalServiceDep):
    return service.get_rental(rental_id)


@router.post("/{rental_id}/end", response_model=RentalOut, responses=_ERRORS)
def end_rental(rental_id: int, payload: RentalEnd, service: RentalServiceDep):
    """Close a rental and release the vehicle back to `available`."""
    return service.end_rental(rental_id, end_date=payload.end_date)
