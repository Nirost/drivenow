from datetime import date, timedelta

import pytest

from app.models.car import CarStatus
from app.services.exceptions import (
    CarNotAvailableError,
    CarNotFoundError,
    RentalAlreadyEndedError,
    RentalNotFoundError,
)


def test_start_rental_marks_car_in_use(car_service, rental_service):
    car = car_service.add_car(model="Nissan Leaf", year=2023)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Bob")

    assert rental.end_date is None
    assert car_service.get_car(car.id).status == CarStatus.IN_USE


def test_start_rental_on_busy_car_raises(car_service, rental_service):
    car = car_service.add_car(model="VW Golf", year=2021)
    rental_service.start_rental(car_id=car.id, customer_name="Carol")

    with pytest.raises(CarNotAvailableError):
        rental_service.start_rental(car_id=car.id, customer_name="Dave")


def test_start_rental_on_car_in_maintenance_raises(car_service, rental_service):
    car = car_service.add_car(model="Skoda Octavia", year=2020)
    car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)

    with pytest.raises(CarNotAvailableError):
        rental_service.start_rental(car_id=car.id, customer_name="Erin")


def test_start_rental_on_missing_car_raises(rental_service):
    with pytest.raises(CarNotFoundError):
        rental_service.start_rental(car_id=999, customer_name="Eve")


def test_failed_rental_leaves_no_partial_state(car_service, rental_service, db_session):
    """
    Regression guard for the transaction bug: a rejected rental must
    leave neither an orphan rental row nor a mutated car status.
    """
    car = car_service.add_car(model="Peugeot 208", year=2021)
    car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)

    with pytest.raises(CarNotAvailableError):
        rental_service.start_rental(car_id=car.id, customer_name="Frank")

    assert rental_service.list_rentals() == []
    assert car_service.get_car(car.id).status == CarStatus.UNDER_MAINTENANCE


def test_end_rental_frees_the_car(car_service, rental_service):
    car = car_service.add_car(model="BMW 3 Series", year=2022)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Grace")

    ended = rental_service.end_rental(rental.id)

    assert ended.end_date is not None
    assert car_service.get_car(car.id).status == CarStatus.AVAILABLE


def test_end_rental_does_not_override_maintenance(car_service, rental_service):
    """A car flagged for maintenance mid-rental must stay in maintenance."""
    car = car_service.add_car(model="Renault Clio", year=2020)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Heidi")
    car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)

    rental_service.end_rental(rental.id)

    assert car_service.get_car(car.id).status == CarStatus.UNDER_MAINTENANCE


def test_end_already_ended_rental_raises(car_service, rental_service):
    car = car_service.add_car(model="Audi A4", year=2022)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Ivan")
    rental_service.end_rental(rental.id)

    with pytest.raises(RentalAlreadyEndedError):
        rental_service.end_rental(rental.id)


def test_end_missing_rental_raises(rental_service):
    with pytest.raises(RentalNotFoundError):
        rental_service.end_rental(4242)


def test_car_can_be_rented_again_after_return(car_service, rental_service):
    car = car_service.add_car(model="Seat Leon", year=2022)
    first = rental_service.start_rental(car_id=car.id, customer_name="Judy")
    rental_service.end_rental(first.id)

    second = rental_service.start_rental(car_id=car.id, customer_name="Ken")

    assert second.id != first.id
    assert car_service.get_car(car.id).status == CarStatus.IN_USE


def test_list_active_rentals_excludes_finished(car_service, rental_service):
    car_a = car_service.add_car(model="Opel Corsa", year=2021)
    car_b = car_service.add_car(model="Volvo V40", year=2022)
    finished = rental_service.start_rental(car_id=car_a.id, customer_name="Leo")
    rental_service.end_rental(finished.id)
    ongoing = rental_service.start_rental(car_id=car_b.id, customer_name="Mia")

    active = rental_service.list_rentals(active_only=True)

    assert [r.id for r in active] == [ongoing.id]


def test_backdated_rental_can_be_ended_today(car_service, rental_service):
    car = car_service.add_car(model="Mini Cooper", year=2021)
    yesterday = date.today() - timedelta(days=1)
    rental = rental_service.start_rental(
        car_id=car.id, customer_name="Nina", start_date=yesterday
    )

    ended = rental_service.end_rental(rental.id)

    assert ended.start_date == yesterday
    assert ended.end_date >= ended.start_date
