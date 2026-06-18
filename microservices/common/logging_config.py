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
