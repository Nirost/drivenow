"""
Domain exceptions.

These carry business meaning only — no HTTP status codes, no FastAPI
imports. The API layer owns the exception-to-status mapping (see
app/api/errors.py), which is what lets this same service layer sit
behind a CLI or a queue consumer unchanged.
"""


class DomainError(Exception):
    """Base class for all business-rule violations."""

    code: str = "domain_error"


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    """The request is valid but conflicts with current state."""

    code = "conflict"


class CarNotFoundError(NotFoundError):
    code = "car_not_found"

    def __init__(self, car_id: int):
        super().__init__(f"Car with id={car_id} was not found")
        self.car_id = car_id


class RentalNotFoundError(NotFoundError):
    code = "rental_not_found"

    def __init__(self, rental_id: int):
        super().__init__(f"Rental with id={rental_id} was not found")
        self.rental_id = rental_id


class CarNotAvailableError(ConflictError):
    code = "car_not_available"

    def __init__(self, car_id: int, status: str):
        super().__init__(f"Car id={car_id} is not available (current status: {status})")
        self.car_id = car_id
        self.status = status


class RentalAlreadyEndedError(ConflictError):
    code = "rental_already_ended"

    def __init__(self, rental_id: int):
        super().__init__(f"Rental id={rental_id} has already ended")
        self.rental_id = rental_id


class CarHasActiveRentalError(ConflictError):
    code = "car_has_active_rental"

    def __init__(self, car_id: int, rental_id: int):
        super().__init__(
            f"Cannot retire car id={car_id}: rental id={rental_id} is still active"
        )
        self.car_id = car_id
        self.rental_id = rental_id


class ConcurrentRentalError(ConflictError):
    """Raised when the DB uniqueness guard rejects a racing rental."""

    code = "concurrent_rental"

    def __init__(self, car_id: int):
        super().__init__(
            f"Car id={car_id} was rented by a concurrent request; please retry"
        )
        self.car_id = car_id


class NoFieldsToUpdateError(DomainError):
    code = "no_fields_to_update"

    def __init__(self) -> None:
        super().__init__("No updatable fields were provided")
