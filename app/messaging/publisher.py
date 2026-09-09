"""
Event publishing.

`EventPublisher` is a Protocol, not a base class: the relay depends on
the interface, and the broker is an implementation detail swapped at
composition time. This is the one place in the project where formal
dependency inversion earns its keep — there are genuinely three
implementations (RabbitMQ, in-memory for tests, null for local runs
without a broker).
"""

from __future__ import annotations

import json
from typing import Protocol

from app.core.logging_config import get_logger
from app.models.outbox import OutboxEvent

logger = get_logger(__name__)


class PublishError(RuntimeError):
    """Raised when an event could not be handed to the broker."""


class EventPublisher(Protocol):
    def publish(self, event: OutboxEvent) -> None:
        """Publish one event. Must raise PublishError on failure."""
        ...

    def close(self) -> None: ...


def serialize(event: OutboxEvent) -> bytes:
    """Wire format. Envelope fields are what consumers deduplicate on."""
    return json.dumps(
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.created_at.isoformat() if event.created_at else None,
            "payload": event.payload,
        }
    ).encode()


class InMemoryPublisher:
    """Records published events. Used by the test suite."""

    def __init__(self) -> None:
        self.published: list[OutboxEvent] = []
        self.fail_next = 0  # force N consecutive failures, for retry tests

    def publish(self, event: OutboxEvent) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise PublishError("simulated broker failure")
        self.published.append(event)

    def close(self) -> None:
        pass


class LoggingPublisher:
    """No broker — logs what would have been sent. For local development."""

    def publish(self, event: OutboxEvent) -> None:
        logger.info("event.published_stdout type=%s id=%s", event.event_type, event.event_id)

    def close(self) -> None:
        pass
