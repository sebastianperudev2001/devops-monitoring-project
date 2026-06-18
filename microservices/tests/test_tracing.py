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
