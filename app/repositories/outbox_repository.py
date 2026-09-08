"""Data access for the transactional outbox."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.outbox import OutboxEvent, OutboxStatus, ProcessedEvent
from app.services.events import DomainEvent


class OutboxRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, event: DomainEvent) -> OutboxEvent:
        """
        Stage an event. Called inside the caller's UnitOfWork, so it
        commits atomically with the business data it describes.
        """
        row = OutboxEvent(
            event_type=event.event_type.value,
            aggregate_type=event.aggregate_type.value,
            aggregate_id=event.aggregate_id,
            payload=event.json_payload(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def fetch_pending(self, limit: int = 100) -> list[OutboxEvent]:
        """
        Claim a batch of pending events for publication.

        FOR UPDATE SKIP LOCKED lets several relay instances run
        concurrently without ever handing the same row to two of them —
        the second worker skips locked rows instead of blocking.

        Ordered by id so events are published in the order they occurred.
        (Note: with multiple relay workers, global ordering is no longer
        guaranteed — see DESIGN.md §10.)
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.db.scalars(stmt))

    def mark_published(self, event: OutboxEvent) -> None:
        event.status = OutboxStatus.PUBLISHED
        event.published_at = datetime.now(timezone.utc)
        event.attempts += 1
        event.last_error = None
        self.db.flush()

    def mark_failure(self, event: OutboxEvent, error: str, max_attempts: int) -> None:
        """Record a failed attempt, dead-lettering once attempts run out."""
        event.attempts += 1
        event.last_error = error[:1000]
        if event.attempts >= max_attempts:
            event.status = OutboxStatus.FAILED
        self.db.flush()

    def count_pending(self) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
        )
        return self.db.scalar(stmt) or 0

    def count_failed(self) -> int:
        stmt = (
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.FAILED)
        )
        return self.db.scalar(stmt) or 0

    # ---- consumer-side idempotency ----

    def already_processed(self, event_id: str, consumer: str) -> bool:
        return (
            self.db.get(ProcessedEvent, {"event_id": event_id, "consumer": consumer})
            is not None
        )

    def mark_processed(self, event_id: str, consumer: str) -> None:
        self.db.add(ProcessedEvent(event_id=event_id, consumer=consumer))
        self.db.flush()
