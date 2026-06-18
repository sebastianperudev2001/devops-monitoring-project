from flask import Flask, jsonify
from prometheus_client import Counter, generate_latest
from opentelemetry import trace
import logging
import random

app = Flask(__name__)
tracer = trace.get_tracer(__name__)

requests_total = Counter('auth_requests_total', 'Total auth requests', ['status'])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/validate')
def validate():
    with tracer.start_as_current_span("auth-validate"):
        # Simular validación (90% success)
        if random.random() < 0.9:
            requests_total.labels(status='200').inc()
            logger.info("Auth validation successful")
            return jsonify({'valid': True, 'user_id': 123})
        else:
            requests_total.labels(status='401').inc()
            logger.warning("Auth validation failed")
            return jsonify({'valid': False}), 401

@app.route('/metrics')
def metrics():
    return generate_latest()

if __name__ == '__main__':
    app.run(port=5001)