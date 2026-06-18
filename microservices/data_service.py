from flask import Flask, jsonify
from prometheus_client import Counter, Histogram, generate_latest
from opentelemetry import trace
import logging
import time
import random

app = Flask(__name__)
tracer = trace.get_tracer(__name__)

requests_total = Counter('data_requests_total', 'Total data requests')
query_duration = Histogram('data_query_duration_seconds', 'Query duration')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/data')
def get_data():
    with tracer.start_as_current_span("data-service-query"):
        # Simular query a DB
        with tracer.start_as_current_span("database-query"):
            with query_duration.time():
                time.sleep(random.uniform(0.1, 0.5))
        
        requests_total.inc()
        logger.info("Data retrieved successfully")
        return jsonify({
            'data': ['item1', 'item2', 'item3'],
            'count': 3
        })

@app.route('/metrics')
def metrics():
    return generate_latest()

if __name__ == '__main__':
    app.run(port=5002)