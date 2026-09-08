"""
Example consumer: customer notifications.

Demonstrates the two things every consumer of an at-least-once stream
must do:
  1. deduplicate on event_id (the relay may republish after a crash)
  2. ack only after successful handling (nack-and-requeue otherwise)

The producer knows nothing about this process. Adding a billing consumer
means writing another one of these and binding it to the exchange — no
change to the API or the service layer.
"""

from __future__ import annotations

import json
import signal
import sys

import pika

from app.core.config import settings
from app.core.database import SessionLocal, UnitOfWork
from app.core.logging_config import get_logger, setup_logging
from app.repositories.outbox_repository import OutboxRepository

logger = get_logger(__name__)

CONSUMER_NAME = "notifications"
QUEUE_NAME = "notifications.rentals"
ROUTING_KEYS = ("rental.started", "rental.ended")

# Messages this consumer rejects without requeueing land here instead of
# being discarded, so a malformed event can still be inspected.
DLX_NAME = "drivenow.events.dlx"
DLQ_NAME = "notifications.rentals.dlq"


def handle_event(envelope: dict) -> None:
    """The actual side effect. Replace with a real email/SMS call."""
    event_type = envelope["event_type"]
    payload = envelope["payload"]

    if event_type == "rental.started":
        logger.info(
            "notify.rental_confirmation customer=%s car_id=%s start=%s",
            payload["customer_name"],
            payload["car_id"],
            payload["start_date"],
        )
    elif event_type == "rental.ended":
        logger.info(
            "notify.return_receipt customer=%s car_id=%s end=%s",
            payload["customer_name"],
            payload["car_id"],
            payload["end_date"],
        )


def on_message(channel, method, properties, body) -> None:
    try:
        envelope = json.loads(body)
        event_id = envelope["event_id"]
    except (ValueError, KeyError):
        # Malformed message: requeuing would loop forever. Reject it to
        # the dead-letter exchange, which keeps it for inspection.
        logger.exception("consumer.malformed_message")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    session = SessionLocal()
    try:
        repo = OutboxRepository(session)
        if repo.already_processed(event_id, CONSUMER_NAME):
            logger.info("consumer.duplicate_skipped event_id=%s", event_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        handle_event(envelope)

        with UnitOfWork(session):
            repo.mark_processed(event_id, CONSUMER_NAME)

        # Ack only after the work AND the idempotency record are durable.
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("consumer.processed event_id=%s type=%s", event_id, envelope["event_type"])
    except Exception:
        logger.exception("consumer.handler_failed event_id=%s", event_id)
        session.rollback()
        # Requeue: this is likely transient (DB blip), so retry later.
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        session.close()


def main() -> None:
    setup_logging()

    params = pika.URLParameters(settings.rabbitmq_url)
    params.heartbeat = 30
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(exchange=settings.events_exchange, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX_NAME, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=DLQ_NAME, durable=True)
    channel.queue_bind(exchange=DLX_NAME, queue=DLQ_NAME)

    channel.queue_declare(
        queue=QUEUE_NAME,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX_NAME},
    )
    for key in ROUTING_KEYS:
        channel.queue_bind(exchange=settings.events_exchange, queue=QUEUE_NAME, routing_key=key)

    # Bounded prefetch: without it a single consumer grabs the whole queue
    # and no other instance gets any work.
    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    def shutdown(*_args):
        logger.info("consumer.shutdown_requested")
        channel.stop_consuming()
        connection.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("consumer.started queue=%s keys=%s", QUEUE_NAME, ROUTING_KEYS)
    channel.start_consuming()
