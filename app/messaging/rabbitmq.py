"""RabbitMQ implementation of EventPublisher (pika, synchronous)."""
from __future__ import annotations

import pika
from pika.exceptions import AMQPError

from app.core.config import settings
from app.core.logging_config import get_logger
from app.messaging.publisher import PublishError, serialize
from app.models.outbox import OutboxEvent

logger = get_logger(__name__)


class RabbitMQPublisher:
    """
    Publishes to a topic exchange, routing on the event type
    ("rental.started"), so consumers bind to the subset they care about
    ("rental.*", "#") without the producer knowing they exist.

    The connection is established lazily and re-established on failure —
    the relay is a long-running process and brokers restart.
    """

    def __init__(self, url: str | None = None, exchange: str | None = None):
        self._url = url or settings.rabbitmq_url
        self._exchange = exchange or settings.events_exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel = None

    def _ensure_channel(self):
        if self._channel is not None and self._channel.is_open:
            return self._channel

        params = pika.URLParameters(self._url)
        params.heartbeat = 30
        params.blocked_connection_timeout = 15
        self._connection = pika.BlockingConnection(params)
        channel = self._connection.channel()
        channel.exchange_declare(
            exchange=self._exchange, exchange_type="topic", durable=True
        )
        # Publisher confirms: publish() only returns successfully once the
        # broker has acknowledged the message. Without this, a "successful"
        # publish can be silently dropped and the outbox row would be
        # marked published anyway.
        channel.confirm_delivery()
        self._channel = channel
        logger.info("rabbitmq.connected exchange=%s", self._exchange)
        return channel

    def publish(self, event: OutboxEvent) -> None:
        try:
            channel = self._ensure_channel()
            channel.basic_publish(
                exchange=self._exchange,
                routing_key=event.event_type,
                body=serialize(event),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,          # persist to disk
                    message_id=event.event_id,
                    type=event.event_type,
                ),
                mandatory=True,
            )
        except AMQPError as exc:
            self._reset()
            raise PublishError(f"AMQP publish failed: {exc}") from exc
        except Exception as exc:
            self._reset()
            raise PublishError(f"publish failed: {exc}") from exc

    def _reset(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        finally:
            self._connection = None
            self._channel = None

    def close(self) -> None:
        self._reset()
