"""
Transactional outbox and relay behaviour.

The point of these tests is the *atomicity* guarantee: an event exists if
and only if the business fact it describes exists.
"""
from app.models.car import CarStatus
from app.models.outbox import OutboxEvent, OutboxStatus
from app.services.exceptions import CarNotAvailableError

import pytest


def _events(db_session):
    return db_session.query(OutboxEvent).order_by(OutboxEvent.id).all()


# ---- the atomicity guarantee ----

def test_successful_rental_writes_an_event(car_service, rental_service, db_session):
    car = car_service.add_car(model="Event Car", year=2023)
    rental_service.start_rental(car_id=car.id, customer_name="Ada")

    types = [e.event_type for e in _events(db_session)]
    assert types == ["car.added", "rental.started"]


def test_rejected_rental_writes_no_event(car_service, rental_service, db_session):
    """
    The core outbox property: a rolled-back transaction must not leave an
    event announcing something that never happened.
    """
    car = car_service.add_car(model="Busy Car", year=2022)
    car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)
    before = len(_events(db_session))

    with pytest.raises(CarNotAvailableError):
        rental_service.start_rental(car_id=car.id, customer_name="Grace")

    assert len(_events(db_session)) == before
    assert not any(e.event_type == "rental.started" for e in _events(db_session))


def test_event_payload_is_json_serializable(car_service, rental_service, db_session):
    """Dates must be ISO strings, not date objects the broker cannot encode."""
    car = car_service.add_car(model="Payload Car", year=2021)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Linus")

    event = [e for e in _events(db_session) if e.event_type == "rental.started"][0]
    assert event.payload["rental_id"] == rental.id
    assert isinstance(event.payload["start_date"], str)
    assert event.aggregate_type == "rental"


def test_ending_a_rental_emits_ended_event(car_service, rental_service, db_session):
    car = car_service.add_car(model="Return Car", year=2020)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Hopper")
    rental_service.end_rental(rental.id)

    ended = [e for e in _events(db_session) if e.event_type == "rental.ended"]
    assert len(ended) == 1
    assert ended[0].payload["end_date"] is not None


def test_events_start_pending_with_unique_ids(car_service, db_session):
    car_service.add_car(model="A", year=2020)
    car_service.add_car(model="B", year=2021)

    events = _events(db_session)
    assert all(e.status == OutboxStatus.PENDING for e in events)
    assert len({e.event_id for e in events}) == len(events)


# ---- relay behaviour ----

def test_relay_publishes_and_marks_events(car_service, rental_service,
                                          relay, publisher, db_session):
    car = car_service.add_car(model="Relay Car", year=2023)
    rental_service.start_rental(car_id=car.id, customer_name="Turing")

    count = relay.process_batch(db_session)

    assert count == 2
    assert len(publisher.published) == 2
    assert all(e.status == OutboxStatus.PUBLISHED for e in _events(db_session))
    assert all(e.published_at is not None for e in _events(db_session))


def test_relay_is_a_noop_when_nothing_pending(relay, publisher, db_session):
    assert relay.process_batch(db_session) == 0
    assert publisher.published == []


def test_published_events_are_not_republished(car_service, relay,
                                              publisher, db_session):
    car_service.add_car(model="Once Only", year=2022)
    relay.process_batch(db_session)

    relay.process_batch(db_session)  # second tick

    assert len(publisher.published) == 1


def test_publish_failure_leaves_event_pending_for_retry(car_service, relay,
                                                        publisher, db_session):
    """A broker outage must not lose the event — it stays pending."""
    car_service.add_car(model="Flaky Broker", year=2022)
    publisher.fail_next = 1

    published = relay.process_batch(db_session)

    assert published == 0
    event = _events(db_session)[0]
    assert event.status == OutboxStatus.PENDING
    assert event.attempts == 1
    assert "simulated" in event.last_error

    # Broker recovers: the same event goes out on the next tick.
    assert relay.process_batch(db_session) == 1
    assert _events(db_session)[0].status == OutboxStatus.PUBLISHED


def test_event_is_dead_lettered_after_max_attempts(car_service, relay,
                                                   publisher, db_session):
    car_service.add_car(model="Poison Pill", year=2022)
    publisher.fail_next = 99  # never succeeds

    for _ in range(relay.max_attempts):
        relay.process_batch(db_session)

    event = _events(db_session)[0]
    assert event.status == OutboxStatus.FAILED
    assert event.attempts == relay.max_attempts


def test_relay_stops_batch_on_broker_failure(car_service, relay,
                                             publisher, db_session):
    """
    One failure means the broker is likely down. Continuing would burn the
    retry budget of every remaining event for no reason.
    """
    for i in range(3):
        car_service.add_car(model=f"Car {i}", year=2020)
    publisher.fail_next = 99

    relay.process_batch(db_session)

    attempts = [e.attempts for e in _events(db_session)]
    assert attempts == [1, 0, 0]


# ---- consumer idempotency ----

def test_consumer_ledger_detects_duplicates(car_service, relay,
                                            outbox_repo, db_session):
    car_service.add_car(model="Dedupe Car", year=2023)
    relay.process_batch(db_session)
    event_id = _events(db_session)[0].event_id

    assert outbox_repo.already_processed(event_id, "notifications") is False
    outbox_repo.mark_processed(event_id, "notifications")
    db_session.commit()

    assert outbox_repo.already_processed(event_id, "notifications") is True
    # Independent consumers track their own progress.
    assert outbox_repo.already_processed(event_id, "billing") is False


def test_outbox_pending_and_failed_counts(car_service, relay,
                                          publisher, outbox_repo, db_session):
    car_service.add_car(model="Counted", year=2022)
    assert outbox_repo.count_pending() == 1

    relay.process_batch(db_session)
    assert outbox_repo.count_pending() == 0
    assert outbox_repo.count_failed() == 0
