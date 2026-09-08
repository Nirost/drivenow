"""
Prometheus metrics.

HTTP latency is captured by middleware (one place, every route) rather
than by a context manager repeated in each handler — that boilerplate
was both noisy and easy to forget on a new endpoint.

Gauges are refreshed from cheap COUNT queries at scrape time, so they
cannot drift from the database the way incrementing counters can.
"""

from prometheus_client import Counter, Gauge, Histogram

http_request_duration_seconds = Histogram(
    "drivenow_http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "endpoint", "status"),
    # Tuned for a local API: sub-millisecond up to ~2s.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

http_requests_total = Counter(
    "drivenow_http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "endpoint", "status"),
)

domain_errors_total = Counter(
    "drivenow_domain_errors_total",
    "Business-rule violations, by error code",
    labelnames=("code",),
)

active_cars_gauge = Gauge(
    "drivenow_active_cars",
    "Cars currently available for rental",
)

fleet_size_gauge = Gauge(
    "drivenow_fleet_size",
    "Total non-retired cars in the fleet",
)

ongoing_rentals_gauge = Gauge(
    "drivenow_ongoing_rentals",
    "Rentals currently in progress",
)


# ---- outbox / messaging ----

outbox_pending_gauge = Gauge(
    "drivenow_outbox_pending",
    "Events written to the outbox but not yet published",
)

outbox_failed_gauge = Gauge(
    "drivenow_outbox_failed",
    "Events dead-lettered after exhausting publish retries",
)

outbox_events_published_total = Counter(
    "drivenow_outbox_events_published_total",
    "Events successfully published to the broker",
    labelnames=("event_type",),
)

outbox_events_failed_total = Counter(
    "drivenow_outbox_events_failed_total",
    "Events dead-lettered after max publish attempts",
    labelnames=("event_type",),
)

outbox_publish_duration_seconds = Histogram(
    "drivenow_outbox_publish_duration_seconds",
    "Time spent handing one event to the broker",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)
