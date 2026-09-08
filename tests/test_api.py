"""
API-layer tests.

These cover what the service tests cannot: status-code mapping, request
validation, and the serialization contract the client actually depends on.
"""


def _add_car(client, model="Tesla Model 3", year=2023):
    return client.post("/cars", json={"model": model, "year": year}).json()


def test_add_car_returns_201_and_body(client):
    response = client.post("/cars", json={"model": "Tesla Model 3", "year": 2023})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "available"
    assert body["model"] == "Tesla Model 3"


def test_invalid_year_returns_422(client):
    response = client.post("/cars", json={"model": "DeLorean", "year": 1815})
    assert response.status_code == 422


def test_empty_patch_returns_422(client):
    car = _add_car(client)
    response = client.patch(f"/cars/{car['id']}", json={})
    assert response.status_code == 422


def test_missing_car_returns_404_with_code(client):
    response = client.get("/cars/9999")

    assert response.status_code == 404
    assert response.json()["code"] == "car_not_found"


def test_renting_busy_car_returns_409(client):
    car = _add_car(client, model="VW Golf", year=2021)
    client.post("/rentals", json={"car_id": car["id"], "customer_name": "A"})

    response = client.post("/rentals", json={"car_id": car["id"], "customer_name": "B"})

    assert response.status_code == 409
    assert response.json()["code"] == "car_not_available"


def test_status_filter_uses_public_name(client):
    _add_car(client, model="Honda Jazz", year=2020)
    response = client.get("/cars", params={"status": "available"})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_pagination_limit_is_bounded(client):
    response = client.get("/cars", params={"limit": 10_000})
    assert response.status_code == 422


def test_full_rental_lifecycle(client):
    car = _add_car(client, model="Fiat Panda", year=2019)

    rental = client.post(
        "/rentals", json={"car_id": car["id"], "customer_name": "Olivia"}
    ).json()
    assert client.get(f"/cars/{car['id']}").json()["status"] == "in_use"

    ended = client.post(f"/rentals/{rental['id']}/end", json={}).json()
    assert ended["end_date"] is not None
    assert client.get(f"/cars/{car['id']}").json()["status"] == "available"


def test_retire_car_with_active_rental_returns_409(client):
    car = _add_car(client, model="Jeep Renegade", year=2022)
    client.post("/rentals", json={"car_id": car["id"], "customer_name": "Pam"})

    response = client.delete(f"/cars/{car['id']}")

    assert response.status_code == 409
    assert response.json()["code"] == "car_has_active_rental"


def test_retire_car_returns_204_and_hides_it(client):
    car = _add_car(client, model="Dacia Duster", year=2021)

    assert client.delete(f"/cars/{car['id']}").status_code == 204
    assert client.get(f"/cars/{car['id']}").status_code == 404


def test_response_carries_correlation_id(client):
    response = client.get("/health/live")
    assert response.headers.get("X-Request-ID")


def test_inbound_correlation_id_is_echoed(client):
    response = client.get("/health/live", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_readiness_reports_database(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_metrics_endpoint_exposes_gauges(client):
    _add_car(client, model="Metric Mobile", year=2024)
    body = client.get("/metrics").text

    assert "drivenow_active_cars" in body
    assert "drivenow_http_request_duration_seconds" in body
