"""Centralized configuration, sourced from environment variables."""
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    # Database
    database_url: str = (
        "postgresql+psycopg2://drivenow:drivenow@localhost:5432/drivenow"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # App
    app_name: str = "DriveNow Vehicle Management System"
    environment: Literal["development", "staging", "production"] = "development"

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/drivenow.log"
    log_json: bool = False  # structured output — enable in production

    # API
    default_page_size: int = 50
    max_page_size: int = 200

    # Messaging / outbox relay
    # "logging" keeps the stack runnable without a broker; docker-compose
    # sets "rabbitmq".
    event_publisher: Literal["rabbitmq", "logging"] = "logging"
    rabbitmq_url: str = "amqp://drivenow:drivenow@localhost:5672/"
    events_exchange: str = "drivenow.events"
    outbox_batch_size: int = 100
    outbox_poll_interval_seconds: float = 1.0
    outbox_max_attempts: int = 5


settings = Settings()
