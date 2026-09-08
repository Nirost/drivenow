"""
Database-level guarantees.

These assert that correctness does not depend on the application layer
behaving: even a direct, service-bypassing write must be rejected.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.car import Car, CarStatus
from app.models.rental import Rental


def test_double_booking_is_impossible_at_db_level(db_session):
    """
    The partial unique index is the real double-booking guard. Two
    ongoing rentals for one car must be unrepresentable, even if a race
    slips past the service-layer status check.
    """
    car = Car(model="Contended Car", year=2022, status=CarStatus.AVAILABLE)
    db_session.add(car)
    db_session.flush()

    db_session.add(Rental(car_id=car.id, customer_name="First", start_date=date.today()))
    db_session.flush()

    db_session.add(Rental(car_id=car.id, customer_name="Second", start_date=date.today()))
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_sequential_rentals_are_allowed(db_session):
    """The index must only constrain *ongoing* rentals, not history."""
    car = Car(model="Busy Car", year=2022, status=CarStatus.AVAILABLE)
    db_session.add(car)
    db_session.flush()

    yesterday = date.today() - timedelta(days=1)
    db_session.add(
        Rental(car_id=car.id, customer_name="First",
               start_date=yesterday, end_date=date.today())
    )
    db_session.flush()

    db_session.add(
        Rental(car_id=car.id, customer_name="Second", start_date=date.today())
    )
    db_session.flush()  # must not raise

    assert len(db_session.query(Rental).all()) == 2


def test_end_date_before_start_date_is_rejected(db_session):
    car = Car(model="Time Traveller", year=2022, status=CarStatus.AVAILABLE)
    db_session.add(car)
    db_session.flush()

    db_session.add(
        Rental(
            car_id=car.id,
            customer_name="Paradox",
            start_date=date.today(),
            end_date=date.today() - timedelta(days=3),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_hard_deleting_a_car_with_history_is_refused(db_session):
    """ON DELETE RESTRICT protects financial history from a stray DELETE."""
    car = Car(model="Historic Car", year=2018, status=CarStatus.AVAILABLE)
    db_session.add(car)
    db_session.flush()
    db_session.add(
        Rental(car_id=car.id, customer_name="Quinn",
               start_date=date.today(), end_date=date.today())
    )
    db_session.flush()

    db_session.delete(car)
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()
