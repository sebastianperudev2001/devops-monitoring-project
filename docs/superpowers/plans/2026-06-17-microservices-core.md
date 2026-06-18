# Microservices Core (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 3-service Flask skeleton (`microservices/{api-gateway,auth-service,data-service}.py`) into a fully instrumented, Docker-ready system with real JWT auth and rate limiting, per `docs/superpowers/specs/2026-06-17-microservices-core-design.md`.

**Architecture:** Three Flask services (Gateway :5000, Auth :5001, Data :5002) sharing a `common/` package for structured JSON logging and OpenTelemetry tracing setup. Gateway adds an in-memory rate limiter and JWT-forwarding aggregation logic; Auth adds real JWT issue/validate; all three add `active_connections`/`errors_total` metrics on top of the existing request counters/histograms.

**Tech Stack:** Flask 3, PyJWT, prometheus-client, OpenTelemetry SDK + OTLP exporter + Flask/requests auto-instrumentation, pytest, responses (HTTP mocking).

---

## File Structure

```
microservices/
├── conftest.py                  # adds microservices/ to sys.path so tests can `import api_gateway` etc.
├── requirements.txt             # done already
├── .venv/                       # done already (gitignored)
├── common/
│   ├── __init__.py
│   ├── logging_config.py        # JSON log formatter + request_id/trace_id context vars
│   └── tracing.py                # OTel TracerProvider + Flask/requests auto-instrumentation setup
├── api_gateway.py                # renamed from api-gateway.py; rate limiter, JWT forwarding, aggregation
├── auth_service.py               # renamed from auth-service.py; JWT login/validate
├── data_service.py               # renamed from data-service.py; simulated DB query
├── Dockerfile.api-gateway
├── Dockerfile.auth-service
├── Dockerfile.data-service
└── tests/
    ├── test_logging_config.py
    ├── test_tracing.py
    ├── test_rate_limiter.py
    ├── test_auth_service.py
    ├── test_data_service.py
    └── test_api_gateway.py
```

The hyphenated skeleton filenames (`api-gateway.py` etc.) can't be imported as Python modules (`import api-gateway` is a syntax error), which blocks writing tests against the Flask `app` objects. Task 1 renames them to underscore form.

`requirements.txt` and `microservices/.venv` already exist (created and verified during planning — all 3 skeleton files import cleanly against the installed versions).

---

### Task 1: Rename skeleton files, add test scaffolding

**Files:**
- Rename: `microservices/api-gateway.py` → `microservices/api_gateway.py`
- Rename: `microservices/auth-service.py` → `microservices/auth_service.py`
- Rename: `microservices/data-service.py` → `microservices/data_service.py`
- Create: `microservices/conftest.py`

- [ ] **Step 1: Rename the three files with git mv**

```bash
git mv microservices/api-gateway.py microservices/api_gateway.py
git mv microservices/auth-service.py microservices/auth_service.py
git mv microservices/data-service.py microservices/data_service.py
```

- [ ] **Step 2: Create `microservices/conftest.py`**

```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 3: Sanity-check the renamed files still import cleanly**

Run: `cd microservices && .venv/bin/python -c "import api_gateway, auth_service, data_service; print('ok')"`
Expected: `ok` (one harmless `NotOpenSSLWarning` from local Python 3.9/LibreSSL is fine)

- [ ] **Step 4: Commit**

```bash
git add microservices/conftest.py
git commit -m "chore: rename microservices to valid python module names, add test scaffolding"
```

---

### Task 2: Shared structured JSON logging

**Files:**
- Create: `microservices/common/__init__.py`
- Create: `microservices/common/logging_config.py`
- Test: `microservices/tests/test_logging_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_logging_config.py
import io
import json

from common.logging_config import configure_logging, set_request_context


def test_configure_logging_outputs_json_with_request_id():
    buffer = io.StringIO()
    logger = configure_logging("test-service", stream=buffer)
    set_request_context("req-123", "trace-abc")

    logger.info("hello world")

    record = json.loads(buffer.getvalue().strip())
    assert record["service"] == "test-service"
    assert record["message"] == "hello world"
    assert record["request_id"] == "req-123"
    assert record["trace_id"] == "trace-abc"
    assert record["level"] == "INFO"


def test_configure_logging_defaults_trace_id_to_none():
    buffer = io.StringIO()
    logger = configure_logging("test-service-2", stream=buffer)
    set_request_context("req-456")

    logger.warning("no trace yet")

    record = json.loads(buffer.getvalue().strip())
    assert record["request_id"] == "req-456"
    assert record["trace_id"] is None
    assert record["level"] == "WARNING"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_logging_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 3: Implement the logging module**

```python
# microservices/common/__init__.py
```

```python
# microservices/common/logging_config.py
import contextvars
import json
import logging
import sys
import uuid

request_id_var = contextvars.ContextVar("request_id", default=None)
trace_id_var = contextvars.ContextVar("trace_id", default=None)


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": self.service_name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id_var.get(),
        }
        return json.dumps(payload)


def configure_logging(service_name, stream=None):
    if stream is None:
        stream = sys.stdout

    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service_name))
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def set_request_context(request_id, trace_id=None):
    request_id_var.set(request_id)
    trace_id_var.set(trace_id)


def extract_or_create_request_id(headers):
    return headers.get("X-Request-ID") or str(uuid.uuid4())
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_logging_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add microservices/common/__init__.py microservices/common/logging_config.py microservices/tests/test_logging_config.py
git commit -m "feat: add shared structured JSON logging module"
```

---

### Task 3: Shared OpenTelemetry tracing setup

**Files:**
- Create: `microservices/common/tracing.py`
- Test: `microservices/tests/test_tracing.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_tracing.py
from common.tracing import resolve_otlp_endpoint, setup_tracing


def test_resolve_otlp_endpoint_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("JAEGER_OTLP_ENDPOINT", raising=False)

    actual = resolve_otlp_endpoint()

    assert actual == "localhost:4317"


def test_resolve_otlp_endpoint_reads_env_var(monkeypatch):
    monkeypatch.setenv("JAEGER_OTLP_ENDPOINT", "jaeger:4317")

    actual = resolve_otlp_endpoint()

    assert actual == "jaeger:4317"


def test_setup_tracing_returns_a_usable_tracer():
    tracer = setup_tracing("test-service-tracing")

    with tracer.start_as_current_span("test-span") as span:
        actual = span

    assert actual is not None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'common.tracing'`

- [ ] **Step 3: Implement the tracing module**

```python
# microservices/common/tracing.py
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def resolve_otlp_endpoint():
    return os.environ.get("JAEGER_OTLP_ENDPOINT", "localhost:4317")


def setup_tracing(service_name, app=None):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=resolve_otlp_endpoint(), insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    RequestsInstrumentor().instrument()
    if app is not None:
        FlaskInstrumentor().instrument_app(app)

    return trace.get_tracer(service_name)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_tracing.py -v`
Expected: 3 passed (a "Overriding of current TracerProvider is not allowed" warning may print if this test file runs after another service module in the same session — harmless, the assertions don't depend on which provider ends up active)

- [ ] **Step 5: Commit**

```bash
git add microservices/common/tracing.py microservices/tests/test_tracing.py
git commit -m "feat: add shared OpenTelemetry tracing setup module"
```

---

### Task 4: Auth Service — real JWT login/validate

**Files:**
- Modify: `microservices/auth_service.py` (full rewrite)
- Test: `microservices/tests/test_auth_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_auth_service.py
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_auth_service.py -v`
Expected: FAIL — `/login` doesn't exist yet (404) and `JWT_SECRET`/`JWT_ALGORITHM` aren't defined in the current file

- [ ] **Step 3: Rewrite `microservices/auth_service.py`**

```python
import os
import time

import jwt
from flask import Flask, g, jsonify, request
from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from common.logging_config import (
    configure_logging,
    extract_or_create_request_id,
    set_request_context,
)
from common.tracing import setup_tracing

app = Flask(__name__)
logger = configure_logging("auth-service")
tracer = setup_tracing("auth-service", app=app)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 15 * 60

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"
DEMO_USER_ID = 123

requests_total = Counter("auth_requests_total", "Total auth requests", ["endpoint", "status"])
request_duration = Histogram("auth_request_duration_seconds", "Request duration", ["endpoint"])
active_connections = Gauge("auth_active_connections", "Active connections")
errors_total = Counter("auth_errors_total", "Total errors", ["error_type"])


@app.before_request
def _before_request():
    g.start_time = time.time()
    active_connections.inc()

    request_id = extract_or_create_request_id(request.headers)
    g.request_id = request_id
    span_context = trace.get_current_span().get_span_context()
    trace_id = format(span_context.trace_id, "032x") if span_context.trace_id else None
    set_request_context(request_id, trace_id)


@app.after_request
def _after_request(response):
    active_connections.dec()
    response.headers["X-Request-ID"] = g.get("request_id", "")
    request_duration.labels(endpoint=request.path).observe(time.time() - g.get("start_time", time.time()))
    return response


def _issue_token(user_id):
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + JWT_EXPIRY_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    password = body.get("password")

    if username == DEMO_USERNAME and password == DEMO_PASSWORD:
        token = _issue_token(DEMO_USER_ID)
        requests_total.labels(endpoint="/login", status="200").inc()
        logger.info("Login successful")
        return jsonify({"token": token})

    requests_total.labels(endpoint="/login", status="401").inc()
    logger.warning("Login failed: invalid credentials")
    return jsonify({"error": "invalid credentials"}), 401


@app.route("/validate")
def validate():
    with tracer.start_as_current_span("auth-validate"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            requests_total.labels(endpoint="/validate", status="401").inc()
            logger.warning("Validation failed: missing bearer token")
            return jsonify({"valid": False, "error": "missing bearer token"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            requests_total.labels(endpoint="/validate", status="200").inc()
            logger.info("Auth validation successful")
            return jsonify({"valid": True, "user_id": payload["sub"]})
        except jwt.ExpiredSignatureError:
            errors_total.labels(error_type="ExpiredSignatureError").inc()
            requests_total.labels(endpoint="/validate", status="401").inc()
            logger.warning("Validation failed: token expired")
            return jsonify({"valid": False, "error": "token expired"}), 401
        except jwt.InvalidTokenError:
            errors_total.labels(error_type="InvalidTokenError").inc()
            requests_total.labels(endpoint="/validate", status="401").inc()
            logger.warning("Validation failed: invalid token")
            return jsonify({"valid": False, "error": "invalid token"}), 401


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return generate_latest()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_auth_service.py -v`
Expected: 6 passed

- [ ] **Step 5: Manual verification — confirm JSON logs end-to-end**

Run:
```bash
cd microservices && .venv/bin/python auth_service.py &
sleep 1
curl -s -X POST localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}'
curl -s localhost:5001/health
kill %1
```
Expected: a JSON token response from `/login`, `{"status": "ok"}` from `/health`, and JSON-formatted log lines (with `service`, `request_id`, `trace_id` fields) printed to stdout while the server was running

- [ ] **Step 6: Commit**

```bash
git add microservices/auth_service.py microservices/tests/test_auth_service.py
git commit -m "feat: replace simulated auth with real JWT login/validate"
```

---

### Task 5: Data Service — metrics, structured logging, tracing

**Files:**
- Modify: `microservices/data_service.py` (full rewrite)
- Test: `microservices/tests/test_data_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_data_service.py
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_data_service.py -v`
Expected: FAIL — `/health` doesn't exist yet and the `data_requests_total` counter has no `endpoint` label yet, so `REGISTRY.get_sample_value` returns `None` and the assertion errors

- [ ] **Step 3: Rewrite `microservices/data_service.py`**

```python
import os
import random
import time

from flask import Flask, g, jsonify, request
from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from common.logging_config import (
    configure_logging,
    extract_or_create_request_id,
    set_request_context,
)
from common.tracing import setup_tracing

app = Flask(__name__)
logger = configure_logging("data-service")
tracer = setup_tracing("data-service", app=app)

requests_total = Counter("data_requests_total", "Total data requests", ["endpoint", "status"])
request_duration = Histogram("data_request_duration_seconds", "Request duration", ["endpoint"])
query_duration = Histogram("data_query_duration_seconds", "Query duration")
active_connections = Gauge("data_active_connections", "Active connections")
errors_total = Counter("data_errors_total", "Total errors", ["error_type"])


@app.before_request
def _before_request():
    g.start_time = time.time()
    active_connections.inc()

    request_id = extract_or_create_request_id(request.headers)
    g.request_id = request_id
    span_context = trace.get_current_span().get_span_context()
    trace_id = format(span_context.trace_id, "032x") if span_context.trace_id else None
    set_request_context(request_id, trace_id)


@app.after_request
def _after_request(response):
    active_connections.dec()
    response.headers["X-Request-ID"] = g.get("request_id", "")
    request_duration.labels(endpoint=request.path).observe(time.time() - g.get("start_time", time.time()))
    return response


@app.route("/data")
def get_data():
    with tracer.start_as_current_span("data-service-query"):
        try:
            with tracer.start_as_current_span("database-query"):
                with query_duration.time():
                    time.sleep(random.uniform(0.1, 0.5))

            requests_total.labels(endpoint="/data", status="200").inc()
            logger.info("Data retrieved successfully")
            return jsonify({"data": ["item1", "item2", "item3"], "count": 3})
        except Exception as e:
            errors_total.labels(error_type=type(e).__name__).inc()
            requests_total.labels(endpoint="/data", status="500").inc()
            logger.error(f"Error in /data: {str(e)}")
            return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return generate_latest()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_data_service.py -v`
Expected: 5 passed

- [ ] **Step 5: Manual verification**

Run:
```bash
cd microservices && .venv/bin/python data_service.py &
sleep 1
curl -s localhost:5002/data
curl -s localhost:5002/metrics | grep data_requests_total
kill %1
```
Expected: the data JSON payload, and a `data_requests_total{endpoint="/data",status="200"} 1.0` line (or similar) in the metrics output

- [ ] **Step 6: Commit**

```bash
git add microservices/data_service.py microservices/tests/test_data_service.py
git commit -m "feat: add active_connections/errors_total metrics and structured logging to data service"
```

---

### Task 6: API Gateway — rate limiter

**Files:**
- Modify: `microservices/api_gateway.py` (add `RateLimiter` class only; rest of the file is rewritten in Task 7)
- Test: `microservices/tests/test_rate_limiter.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_rate_limiter.py
from api_gateway import RateLimiter


def test_allows_requests_under_the_limit():
    limiter = RateLimiter(limit=3, window_seconds=10)

    first = limiter.is_allowed("1.2.3.4", now=0)
    second = limiter.is_allowed("1.2.3.4", now=1)
    third = limiter.is_allowed("1.2.3.4", now=2)

    assert first is True
    assert second is True
    assert third is True


def test_rejects_requests_over_the_limit_within_window():
    limiter = RateLimiter(limit=2, window_seconds=10)

    first = limiter.is_allowed("1.2.3.4", now=0)
    second = limiter.is_allowed("1.2.3.4", now=1)
    third = limiter.is_allowed("1.2.3.4", now=2)

    assert first is True
    assert second is True
    assert third is False


def test_allows_again_after_window_expires():
    limiter = RateLimiter(limit=1, window_seconds=10)

    within_limit = limiter.is_allowed("1.2.3.4", now=0)
    still_in_window = limiter.is_allowed("1.2.3.4", now=5)
    new_window = limiter.is_allowed("1.2.3.4", now=11)

    assert within_limit is True
    assert still_in_window is False
    assert new_window is True


def test_tracks_separate_clients_independently():
    limiter = RateLimiter(limit=1, window_seconds=10)

    first_client = limiter.is_allowed("1.1.1.1", now=0)
    second_client = limiter.is_allowed("2.2.2.2", now=0)

    assert first_client is True
    assert second_client is True
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_rate_limiter.py -v`
Expected: FAIL with `ImportError: cannot import name 'RateLimiter' from 'api_gateway'`

- [ ] **Step 3: Add the `RateLimiter` class to `microservices/api_gateway.py`**

Insert this near the top of the file, right after the existing imports (the rest of the file is still the old skeleton — that's fixed in Task 7):

```python
import time


class RateLimiter:
    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows = {}

    def is_allowed(self, key, now=None):
        now = time.time() if now is None else now
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= self.window_seconds:
            self._windows[key] = (now, 1)
            return True

        if count < self.limit:
            self._windows[key] = (window_start, count + 1)
            return True

        return False
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_rate_limiter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add microservices/api_gateway.py microservices/tests/test_rate_limiter.py
git commit -m "feat: add in-memory fixed-window rate limiter to API Gateway"
```

---

### Task 7: API Gateway — full rewrite (JWT forwarding, logging, tracing, metrics, rate-limiter wiring)

**Files:**
- Modify: `microservices/api_gateway.py` (replace everything except the `RateLimiter` class from Task 6)
- Test: `microservices/tests/test_api_gateway.py`

- [ ] **Step 1: Write the failing tests**

```python
# microservices/tests/test_api_gateway.py
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd microservices && .venv/bin/pytest tests/test_api_gateway.py -v`
Expected: FAIL — `/health` doesn't exist yet, `/api/data` doesn't check for an `Authorization` header yet, and `AUTH_SERVICE_URL`/`DATA_SERVICE_URL` aren't defined yet

- [ ] **Step 3: Rewrite `microservices/api_gateway.py`**

```python
import os
import time

import requests
from flask import Flask, g, jsonify, request
from opentelemetry import trace
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from common.logging_config import (
    configure_logging,
    extract_or_create_request_id,
    set_request_context,
)
from common.tracing import setup_tracing

app = Flask(__name__)
logger = configure_logging("api-gateway")
tracer = setup_tracing("api-gateway", app=app)

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:5001")
DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:5002")

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 20))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 10))

requests_total = Counter("gateway_requests_total", "Total requests", ["endpoint", "status"])
request_duration = Histogram("gateway_request_duration_seconds", "Request duration", ["endpoint"])
active_connections = Gauge("gateway_active_connections", "Active connections")
errors_total = Counter("gateway_errors_total", "Total errors", ["error_type"])
throttled_total = Counter("gateway_throttled_total", "Total throttled requests")


class RateLimiter:
    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows = {}

    def is_allowed(self, key, now=None):
        now = time.time() if now is None else now
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= self.window_seconds:
            self._windows[key] = (now, 1)
            return True

        if count < self.limit:
            self._windows[key] = (window_start, count + 1)
            return True

        return False


rate_limiter = RateLimiter(limit=RATE_LIMIT, window_seconds=RATE_LIMIT_WINDOW_SECONDS)


@app.before_request
def _before_request():
    g.start_time = time.time()
    active_connections.inc()

    request_id = extract_or_create_request_id(request.headers)
    g.request_id = request_id
    span_context = trace.get_current_span().get_span_context()
    trace_id = format(span_context.trace_id, "032x") if span_context.trace_id else None
    set_request_context(request_id, trace_id)

    if not rate_limiter.is_allowed(request.remote_addr):
        throttled_total.inc()
        logger.warning(f"Rate limit exceeded for {request.remote_addr}")
        return jsonify({"error": "rate limit exceeded"}), 429


@app.after_request
def _after_request(response):
    active_connections.dec()
    response.headers["X-Request-ID"] = g.get("request_id", "")
    request_duration.labels(endpoint=request.path).observe(time.time() - g.get("start_time", time.time()))
    return response


@app.route("/api/data")
def get_data():
    with tracer.start_as_current_span("api-gateway-get-data"):
        forward_headers = {"X-Request-ID": g.get("request_id", "")}
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            requests_total.labels(endpoint="/api/data", status="401").inc()
            logger.warning("Rejected request with no Authorization header")
            return jsonify({"error": "Unauthorized"}), 401

        try:
            with tracer.start_as_current_span("call-auth-service"):
                auth_resp = requests.get(
                    f"{AUTH_SERVICE_URL}/validate",
                    headers={**forward_headers, "Authorization": auth_header},
                    timeout=2,
                )

            if auth_resp.status_code != 200:
                requests_total.labels(endpoint="/api/data", status="401").inc()
                logger.warning("Auth service rejected the request")
                return jsonify({"error": "Unauthorized"}), 401

            with tracer.start_as_current_span("call-data-service"):
                data_resp = requests.get(
                    f"{DATA_SERVICE_URL}/data",
                    headers=forward_headers,
                    timeout=2,
                )

            requests_total.labels(endpoint="/api/data", status="200").inc()
            logger.info("Successfully served /api/data")
            return data_resp.json()

        except Exception as e:
            errors_total.labels(error_type=type(e).__name__).inc()
            requests_total.labels(endpoint="/api/data", status="500").inc()
            logger.error(f"Error in /api/data: {str(e)}")
            return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return generate_latest()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd microservices && .venv/bin/pytest tests/test_api_gateway.py tests/test_rate_limiter.py -v`
Expected: 9 passed

- [ ] **Step 5: Manual verification**

Run:
```bash
cd microservices
.venv/bin/python auth_service.py &
.venv/bin/python data_service.py &
.venv/bin/python api_gateway.py &
sleep 1
TOKEN=$(curl -s -X POST localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -s localhost:5000/api/data -H "Authorization: Bearer $TOKEN"
curl -s localhost:5000/api/data
kill %1 %2 %3
```
Expected: the first curl (with token) returns the aggregated data JSON; the second (no token) returns `{"error": "Unauthorized"}` with a 401

- [ ] **Step 6: Commit**

```bash
git add microservices/api_gateway.py microservices/tests/test_api_gateway.py
git commit -m "feat: wire JWT forwarding, rate limiting, logging, tracing and metrics into API Gateway"
```

---

### Task 8: Dockerfiles for all three services

**Files:**
- Create: `microservices/Dockerfile.api-gateway`
- Create: `microservices/Dockerfile.auth-service`
- Create: `microservices/Dockerfile.data-service`

- [ ] **Step 1: Write `microservices/Dockerfile.api-gateway`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY api_gateway.py .

RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

CMD ["python", "api_gateway.py"]
```

- [ ] **Step 2: Write `microservices/Dockerfile.auth-service`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY auth_service.py .

RUN useradd --create-home appuser
USER appuser

EXPOSE 5001

CMD ["python", "auth_service.py"]
```

- [ ] **Step 3: Write `microservices/Dockerfile.data-service`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY data_service.py .

RUN useradd --create-home appuser
USER appuser

EXPOSE 5002

CMD ["python", "data_service.py"]
```

- [ ] **Step 4: Build all three images**

Run:
```bash
cd microservices
docker build -f Dockerfile.api-gateway -t devops-monitoring/api-gateway:phase1 .
docker build -f Dockerfile.auth-service -t devops-monitoring/auth-service:phase1 .
docker build -f Dockerfile.data-service -t devops-monitoring/data-service:phase1 .
```
Expected: all three builds finish with `Successfully tagged ...` (or BuildKit's equivalent final line)

- [ ] **Step 5: Smoke-test each container standalone**

Run:
```bash
docker run -d --rm --name auth-test -p 5001:5001 devops-monitoring/auth-service:phase1
docker run -d --rm --name data-test -p 5002:5002 devops-monitoring/data-service:phase1
docker run -d --rm --name gateway-test -p 5000:5000 devops-monitoring/api-gateway:phase1
sleep 2
curl -s localhost:5001/health
curl -s localhost:5002/health
curl -s localhost:5000/health
docker stop auth-test data-test gateway-test
```
Expected: `{"status": "ok"}` from all three `/health` calls (the Gateway container can't reach the other two services yet since they're not networked together — that's Phase 2's Docker Compose job — but it should still start and serve `/health`/`/metrics` on its own)

- [ ] **Step 6: Run the full test suite one more time**

Run: `cd microservices && .venv/bin/pytest tests/ -v`
Expected: 25 passed (2 logging + 3 tracing + 4 rate limiter + 6 auth + 5 data + 5 gateway)

- [ ] **Step 7: Commit**

```bash
git add microservices/Dockerfile.api-gateway microservices/Dockerfile.auth-service microservices/Dockerfile.data-service
git commit -m "feat: add per-service Dockerfiles for Phase 1 microservices"
```

---

## Phase 1 Done — Next Up

Phase 2 (Docker Compose observability stack: Prometheus, Grafana, Loki+Promtail, Jaeger, Alertmanager) gets its own design spec and plan once this phase is merged, per the roadmap in `docs/superpowers/specs/2026-06-17-microservices-core-design.md`.
