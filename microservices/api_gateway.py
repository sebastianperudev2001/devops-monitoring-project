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
