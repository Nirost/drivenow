"""
Outbox relay.

Polls the outbox for pending events, publishes them, and marks them sent.
Runs as its own process so a slow or unavailable broker can never add
latency to (or fail) an API request.

Delivery semantics: at-least-once. If the process dies after a successful
publish but before the status update, the event is republished on the
next tick. Consumers deduplicate on `event_id` — see
app/consumers/notifications.py.
"""
from __future__ import annotations

import signal
import time

from app.core.config import settings
from app.core.database import SessionLocal, UnitOfWork
from app.core.logging_config import get_logger, setup_logging
from app.core.metrics import (
    outbox_events_failed_total,
    outbox_events_published_total,
    outbox_publish_duration_seconds,
)
from app.messaging.publisher import EventPublisher, PublishError
from app.repositories.outbox_repository import OutboxRepository

logger = get_logger(__name__)


class OutboxRelay:
    def __init__(self, publisher: EventPublisher,
                 batch_size: int | None = None,
                 poll_interval: float | None = None,
                 max_attempts: int | None = None):
        self.publisher = publisher
        self.batch_size = batch_size or settings.outbox_batch_size
        self.poll_interval = poll_interval or settings.outbox_poll_interval_seconds
        self.max_attempts = max_attempts or settings.outbox_max_attempts
        self._running = False

    def process_batch(self, session) -> int:
        """
        Publish one batch. Returns the number successfully published.

        Each event is committed individually rather than per batch: a
        single poison message must not roll back the successful
        publications that preceded it in the same batch.
        """
        repo = OutboxRepository(session)
        uow = UnitOfWork(session)

        events = repo.fetch_pending(limit=self.batch_size)
        if not events:
            return 0

        published = 0
        for event in events:
            try:
                with outbox_publish_duration_seconds.time():
                    self.publisher.publish(event)
            except PublishError as exc:
                logger.warning(
                    "outbox.publish_failed event_id=%s attempts=%s: %s",
                    event.event_id, event.attempts + 1, exc,
                )
                with uow:
                    repo.mark_failure(event, str(exc), self.max_attempts)
                if event.attempts >= self.max_attempts:
                    outbox_events_failed_total.labels(
                        event_type=event.event_type
                    ).inc()
                    logger.error(
                        "outbox.dead_lettered event_id=%s type=%s",
                        event.event_id, event.event_type,
                    )
                # Stop the batch: if the broker is down, the remaining
                # events will fail too. Burning their retry budget on a
                # known-bad broker would dead-letter them needlessly.
                break
            else:
                with uow:
                    repo.mark_published(event)
                outbox_events_published_total.labels(
                    event_type=event.event_type
                ).inc()
                published += 1
                logger.info(
                    "outbox.published event_id=%s type=%s",
                    event.event_id, event.event_type,
                )
        return published

    def run_forever(self) -> None:
        self._running = True
        self._install_signal_handlers()
        logger.info(
            "relay.started batch_size=%s poll_interval=%ss",
            self.batch_size, self.poll_interval,
        )

        while self._running:
            session = SessionLocal()
            try:
                count = self.process_batch(session)
            except Exception:
                logger.exception("relay.batch_error")
                session.rollback()
                count = 0
            finally:
                session.close()

            # Only sleep when idle — a full batch probably means more work
            # is waiting, so drain the backlog before pausing.
            if count < self.batch_size:
                time.sleep(self.poll_interval)

        self.publisher.close()
        logger.info("relay.stopped")

    def stop(self, *_args) -> None:
        logger.info("relay.shutdown_requested")
        self._running = False

    def _install_signal_handlers(self) -> None:
        # Graceful shutdown: finish the in-flight event rather than being
        # killed mid-publish when the container is stopped.
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)


def build_publisher() -> EventPublisher:
    """Composition root for the relay process."""
    if settings.event_publisher == "rabbitmq":
        from app.messaging.rabbitmq import RabbitMQPublisher

        return RabbitMQPublisher()
    from app.messaging.publisher import LoggingPublisher

    return LoggingPublisher()


def main() -> None:
    setup_logging()
    OutboxRelay(build_publisher()).run_forever()
