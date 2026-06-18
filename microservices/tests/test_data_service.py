import pytest
from prometheus_client import REGISTRY

from data_service import app


@pytest.fixture
def client():
    return app.test_client()


def test_get_data_returns_expected_shape(client):
    resp = client.get("/data")

    assert resp.status_code == 200
    assert resp.get_json() == {"data": ["item1", "item2", "item3"], "count": 3}


def test_get_data_sets_request_id_header_when_absent(client):
    resp = client.get("/data")

    assert resp.headers.get("X-Request-ID")


def test_get_data_reuses_inbound_request_id_header(client):
    resp = client.get("/data", headers={"X-Request-ID": "fixed-id-123"})

    assert resp.headers.get("X-Request-ID") == "fixed-id-123"


def test_get_data_increments_requests_total_counter(client):
    before = REGISTRY.get_sample_value("data_requests_total", {"endpoint": "/data", "status": "200"}) or 0

    client.get("/data")

    after = REGISTRY.get_sample_value("data_requests_total", {"endpoint": "/data", "status": "200"})
    assert after == before + 1


def test_health_returns_ok(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
