"""Data access for the transactional outbox."""

from datetime import UTC, datetime

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

    def fetch_pending_ids(self, limit: int = 100) -> list[int]:
        """
        Peek at the ids of pending events, oldest first.

        Deliberately takes no lock: the relay commits after every event,
        and a commit releases every lock held by that transaction. Locking
        the whole batch up front would therefore protect only the first
        event — the rest would sit unlocked while another worker claimed
        them. Each event is locked individually by `claim` instead.
        """
        stmt = (
            select(OutboxEvent.id)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.id)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def claim(self, event_id: int) -> OutboxEvent | None:
        """
        Take a row lock on one pending event, for the duration of the
        caller's transaction — which spans the publish and the status
        update, so the lock is still held when the row is marked sent.

        SKIP LOCKED returns None if another relay worker holds it. The
        status re-check closes the window between the peek and the lock,
        where a competing worker may have already published it.
        """
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == OutboxStatus.PENDING,
            )
            .with_for_update(skip_locked=True)
        )
        return self.db.scalars(stmt).first()

    def mark_published(self, event: OutboxEvent) -> None:
        event.status = OutboxStatus.PUBLISHED
        event.published_at = datetime.now(UTC)
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
        return self.db.get(ProcessedEvent, {"event_id": event_id, "consumer": consumer}) is not None

    def mark_processed(self, event_id: str, consumer: str) -> None:
        self.db.add(ProcessedEvent(event_id=event_id, consumer=consumer))
        self.db.flush()
