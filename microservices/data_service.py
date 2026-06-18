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
