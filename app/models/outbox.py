"""
Transactional outbox.

An event row is written in the SAME transaction as the business data it
describes, so the two commit together or not at all. A separate relay
process publishes rows to the broker afterwards.

This is what makes "the rental exists but billing never heard about it"
impossible — the failure mode of publishing directly after COMMIT.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"  # dead-lettered after max_attempts


def _new_event_id() -> str:
    return uuid.uuid4().hex


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    # Autoincrement id doubles as the publication order.
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Stable business identity of the event. Consumers deduplicate on
    # this, which is what makes at-least-once delivery safe.
    event_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, default=_new_event_id
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # JSONB on PostgreSQL, plain JSON on SQLite so the test suite works.
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )

    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, native_enum=False, length=16),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The relay polls "pending, oldest first" on every tick. A partial
        # index keeps that query cheap even when the table has millions of
        # already-published rows.
        Index(
            "ix_outbox_pending",
            "id",
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )

    def __repr__(self) -> str:
        return f"<OutboxEvent id={self.id} type={self.event_type} status={self.status.value}>"


class ProcessedEvent(Base):
    """
    Consumer-side idempotency ledger.

    At-least-once delivery means a consumer WILL occasionally see the same
    event twice (relay published, then crashed before marking it sent).
    Recording processed event_ids makes reprocessing a no-op.

    Colocated here for the exercise; in production each consumer owns its
    own store, so a consumer's bookkeeping cannot couple to the producer's
    database.
    """

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
