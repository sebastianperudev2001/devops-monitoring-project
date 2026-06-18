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
