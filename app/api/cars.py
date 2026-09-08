"""
Car endpoints.

No try/except here by design — domain exceptions are translated to HTTP
centrally in app/api/errors.py.
"""

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CarServiceDep, PaginationDep
from app.api.schemas import CarCreate, CarOut, CarUpdate, ErrorResponse
from app.models.car import CarStatus

router = APIRouter(prefix="/cars", tags=["cars"])

_ERRORS = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}


@router.post("", response_model=CarOut, status_code=status.HTTP_201_CREATED)
def add_car(payload: CarCreate, service: CarServiceDep):
    """Register a new vehicle. Starts as `available`."""
    return service.add_car(model=payload.model, year=payload.year)


@router.get("", response_model=list[CarOut])
def list_cars(
    service: CarServiceDep,
    page: PaginationDep,
    car_status: CarStatus | None = Query(
        default=None, alias="status", description="Filter by vehicle status"
    ),
):
    """List vehicles, newest id last. Retired vehicles are excluded."""
    return service.list_cars(status=car_status, limit=page.limit, offset=page.offset)


@router.get("/{car_id}", response_model=CarOut, responses=_ERRORS)
def get_car(car_id: int, service: CarServiceDep):
    return service.get_car(car_id)


@router.patch("/{car_id}", response_model=CarOut, responses=_ERRORS)
def update_car(car_id: int, payload: CarUpdate, service: CarServiceDep):
    """Partial update. Fields omitted from the body are left untouched."""
    return service.update_car(car_id, **payload.model_dump(exclude_unset=True))


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
def retire_car(car_id: int, service: CarServiceDep):
    """
    Retire a vehicle (soft delete). Rental history is preserved.
    Rejected with 409 while a rental is still active.
    """
    service.retire_car(car_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
