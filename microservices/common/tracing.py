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
