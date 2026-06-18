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
