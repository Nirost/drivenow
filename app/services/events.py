"""
Domain event definitions.

Events are part of the system's public contract — once a consumer depends
on `rental.started`, its shape cannot change casually. Defining them in
one typed place (rather than inline dicts at each call site) is what makes
that contract reviewable.
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    CAR_ADDED = "car.added"
    CAR_RETIRED = "car.retired"
    RENTAL_STARTED = "rental.started"
    RENTAL_ENDED = "rental.ended"


class AggregateType(str, Enum):
    CAR = "car"
    RENTAL = "rental"


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass(frozen=True)
class DomainEvent:
    """An event awaiting persistence to the outbox."""

    event_type: EventType
    aggregate_type: AggregateType
    aggregate_id: str
    payload: dict[str, Any]

    def json_payload(self) -> dict[str, Any]:
        """JSON-safe payload — dates become ISO strings, enums their values."""
        return {key: _serialize(value) for key, value in self.payload.items()}


def rental_started(rental) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.RENTAL_STARTED,
        aggregate_type=AggregateType.RENTAL,
        aggregate_id=str(rental.id),
        payload={
            "rental_id": rental.id,
            "car_id": rental.car_id,
            "customer_name": rental.customer_name,
            "start_date": rental.start_date,
        },
    )


def rental_ended(rental) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.RENTAL_ENDED,
        aggregate_type=AggregateType.RENTAL,
        aggregate_id=str(rental.id),
        payload={
            "rental_id": rental.id,
            "car_id": rental.car_id,
            "customer_name": rental.customer_name,
            "start_date": rental.start_date,
            "end_date": rental.end_date,
        },
    )


def car_added(car) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.CAR_ADDED,
        aggregate_type=AggregateType.CAR,
        aggregate_id=str(car.id),
        payload={"car_id": car.id, "model": car.model, "year": car.year},
    )


def car_retired(car) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.CAR_RETIRED,
        aggregate_type=AggregateType.CAR,
        aggregate_id=str(car.id),
        payload={"car_id": car.id, "model": car.model},
    )
