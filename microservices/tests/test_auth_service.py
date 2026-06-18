import time

import jwt
import pytest

from auth_service import JWT_ALGORITHM, JWT_SECRET, app


@pytest.fixture
def client():
    return app.test_client()


def test_login_with_valid_credentials_returns_token(client):
    resp = client.post("/login", json={"username": "demo", "password": "demo123"})

    assert resp.status_code == 200
    payload = jwt.decode(resp.get_json()["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["sub"] == 123


def test_login_with_invalid_credentials_returns_401(client):
    resp = client.post("/login", json={"username": "demo", "password": "wrong"})

    assert resp.status_code == 401


def test_validate_with_fresh_token_returns_valid(client):
    login_resp = client.post("/login", json={"username": "demo", "password": "demo123"})
    token = login_resp.get_json()["token"]

    resp = client.get("/validate", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.get_json() == {"valid": True, "user_id": 123}


def test_validate_with_expired_token_returns_401(client):
    now = int(time.time())
    expired_token = jwt.encode(
        {"sub": 123, "iat": now - 1000, "exp": now - 100},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    resp = client.get("/validate", headers={"Authorization": f"Bearer {expired_token}"})

    assert resp.status_code == 401
    assert resp.get_json()["valid"] is False


def test_validate_with_tampered_token_returns_401(client):
    resp = client.get("/validate", headers={"Authorization": "Bearer not-a-real-token"})

    assert resp.status_code == 401
    assert resp.get_json()["valid"] is False


def test_validate_without_authorization_header_returns_401(client):
    resp = client.get("/validate")

    assert resp.status_code == 401
