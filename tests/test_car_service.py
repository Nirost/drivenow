import pytest

from app.models.car import CarStatus
from app.services.exceptions import (
    CarHasActiveRentalError,
    CarNotFoundError,
    InvalidStatusTransitionError,
    NoFieldsToUpdateError,
)


def test_add_car_defaults_to_available(car_service):
    car = car_service.add_car(model="Toyota Corolla", year=2022)
    assert car.id is not None
    assert car.status == CarStatus.AVAILABLE


def test_get_missing_car_raises(car_service):
    with pytest.raises(CarNotFoundError):
        car_service.get_car(999)


def test_list_cars_filters_by_status(car_service):
    car_service.add_car(model="Honda Civic", year=2021)
    car2 = car_service.add_car(model="Ford Focus", year=2020)
    car_service.update_car(car2.id, status=CarStatus.UNDER_MAINTENANCE)

    assert len(car_service.list_cars(status=CarStatus.AVAILABLE)) == 1
    maintenance = car_service.list_cars(status=CarStatus.UNDER_MAINTENANCE)
    assert [c.id for c in maintenance] == [car2.id]


def test_update_with_no_fields_raises(car_service):
    car = car_service.add_car(model="Mazda 3", year=2023)
    with pytest.raises(NoFieldsToUpdateError):
        car_service.update_car(car.id)


def test_partial_update_leaves_other_fields_untouched(car_service):
    car = car_service.add_car(model="Mazda 3", year=2023)
    updated = car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)
    assert updated.status == CarStatus.UNDER_MAINTENANCE
    assert updated.model == "Mazda 3"
    assert updated.year == 2023


def test_retire_car_with_active_rental_is_blocked(car_service, rental_service):
    car = car_service.add_car(model="Kia Sportage", year=2022)
    rental_service.start_rental(car_id=car.id, customer_name="Alice")

    with pytest.raises(CarHasActiveRentalError):
        car_service.retire_car(car.id)


def test_retired_car_is_hidden_but_history_survives(car_service, rental_service):
    """Retiring must not destroy the rental record that references it."""
    car = car_service.add_car(model="Fiat 500", year=2019)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Bob")
    rental_service.end_rental(rental.id)

    car_service.retire_car(car.id)

    assert car.id not in [c.id for c in car_service.list_cars()]
    with pytest.raises(CarNotFoundError):
        car_service.get_car(car.id)
    # The rental history is still intact and still points at the car.
    assert rental_service.get_rental(rental.id).car_id == car.id


def test_in_use_cannot_be_set_directly(car_service):
    """A car in use with no rental behind it is unrepresentable state."""
    car = car_service.add_car(model="Kia Ceed", year=2021)

    with pytest.raises(InvalidStatusTransitionError):
        car_service.update_car(car.id, status=CarStatus.IN_USE)

    assert car_service.get_car(car.id).status == CarStatus.AVAILABLE


def test_cannot_free_a_car_that_is_still_rented(car_service, rental_service):
    car = car_service.add_car(model="Skoda Fabia", year=2020)
    rental_service.start_rental(car_id=car.id, customer_name="Ruth")

    with pytest.raises(InvalidStatusTransitionError):
        car_service.update_car(car.id, status=CarStatus.AVAILABLE)

    assert car_service.get_car(car.id).status == CarStatus.IN_USE


def test_rented_car_can_still_be_flagged_for_maintenance(car_service, rental_service):
    """
    Deliberately allowed: the car is genuinely unavailable, and ending the
    rental will not release a car it did not leave IN_USE.
    """
    car = car_service.add_car(model="Nissan Micra", year=2019)
    rental = rental_service.start_rental(car_id=car.id, customer_name="Sam")

    car_service.update_car(car.id, status=CarStatus.UNDER_MAINTENANCE)
    rental_service.end_rental(rental.id)

    assert car_service.get_car(car.id).status == CarStatus.UNDER_MAINTENANCE
