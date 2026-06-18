from flask import Flask, jsonify
import requests
from prometheus_client import Counter, Histogram, generate_latest
from opentelemetry import trace
import logging

app = Flask(__name__)
tracer = trace.get_tracer(__name__)

# Metrics
requests_total = Counter('gateway_requests_total', 'Total requests', ['endpoint', 'status'])
request_duration = Histogram('gateway_request_duration_seconds', 'Request duration')

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.route('/api/data')
@request_duration.time()
def get_data():
    with tracer.start_as_current_span("api-gateway-get-data"):
        try:
            # Call auth service
            with tracer.start_as_current_span("call-auth-service"):
                auth_resp = requests.get('http://localhost:5001/validate', timeout=1)
            
            if auth_resp.status_code != 200:
                requests_total.labels(endpoint='/api/data', status='401').inc()
                return jsonify({'error': 'Unauthorized'}), 401
            
            # Call data service
            with tracer.start_as_current_span("call-data-service"):
                data_resp = requests.get('http://localhost:5002/data', timeout=1)
            
            requests_total.labels(endpoint='/api/data', status='200').inc()
            logger.info(f"Successfully served /api/data")
            return data_resp.json()
        
        except Exception as e:
            requests_total.labels(endpoint='/api/data', status='500').inc()
            logger.error(f"Error in /api/data: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/metrics')
def metrics():
    return generate_latest()

if __name__ == '__main__':
    app.run(port=5000)