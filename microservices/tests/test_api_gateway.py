import pytest
import responses
from requests.exceptions import ConnectionError as RequestsConnectionError

import api_gateway
from api_gateway import AUTH_SERVICE_URL, DATA_SERVICE_URL, RateLimiter, app


@pytest.fixture
def client():
    return app.test_client()


def test_get_data_without_authorization_header_returns_401(client):
    resp = client.get("/api/data")

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Unauthorized"}


@responses.activate
def test_get_data_with_invalid_token_returns_401(client):
    responses.add(
        responses.GET,
        f"{AUTH_SERVICE_URL}/validate",
        json={"valid": False, "error": "invalid token"},
        status=401,
    )

    resp = client.get("/api/data", headers={"Authorization": "Bearer bad-token"})

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Unauthorized"}


@responses.activate
def test_get_data_with_valid_token_returns_aggregated_data(client):
    responses.add(
        responses.GET,
        f"{AUTH_SERVICE_URL}/validate",
        json={"valid": True, "user_id": 123},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{DATA_SERVICE_URL}/data",
        json={"data": ["item1", "item2", "item3"], "count": 3},
        status=200,
    )

    resp = client.get("/api/data", headers={"Authorization": "Bearer good-token"})

    assert resp.status_code == 200
    assert resp.get_json() == {"data": ["item1", "item2", "item3"], "count": 3}


@responses.activate
def test_get_data_returns_500_when_data_service_raises(client):
    responses.add(
        responses.GET,
        f"{AUTH_SERVICE_URL}/validate",
        json={"valid": True, "user_id": 123},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{DATA_SERVICE_URL}/data",
        body=RequestsConnectionError("data service unreachable"),
    )

    resp = client.get("/api/data", headers={"Authorization": "Bearer good-token"})

    assert resp.status_code == 500


def test_rate_limiter_blocks_requests_over_the_limit(client, monkeypatch):
    monkeypatch.setattr(api_gateway, "rate_limiter", RateLimiter(limit=2, window_seconds=10))

    r1 = client.get("/health")
    r2 = client.get("/health")
    r3 = client.get("/health")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
