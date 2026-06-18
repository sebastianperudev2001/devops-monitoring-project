# Phase 1: Microservices Core — Design Spec

**Status:** Approved
**Date:** 2026-06-17
**Phase:** 1 of 8 (see Project Roadmap below)

## Context

This is the final project for a 3-day DevSecOps/Observability course (see `Instrucciones.html`).
The full project is too large for a single spec, so it's decomposed into 8 phases, each with
its own design spec and implementation plan:

1. **Microservices core** (this spec)
2. Observability stack (Docker Compose: Prometheus, Grafana, Loki+Promtail, Jaeger, Alertmanager)
3. Prometheus rules & alerting (recording rules, 5+ alerts, Alertmanager → Slack)
4. Grafana dashboards (Service Overview, Business Metrics, Security w/ CVE metrics)
5. Security pipeline (trufflehog/semgrep/pip-audit/trivy + vulnerability report)
6. CI/CD (GitHub Actions: tests + security pipeline + image build)
7. Kubernetes + Helm + Istio (service mesh with automatic tracing)
8. Docs & reflection answers

A skeleton of the 3 services already exists at `microservices/{api-gateway,auth-service,data-service}.py`,
copied verbatim from the instructions doc. They run but are not yet docker-ready, lack real auth,
lack rate limiting, lack active-connections/error-type metrics, log in plain text instead of JSON,
and don't propagate trace context between services (spans are created but never exported — no
`TracerProvider` is configured, and the `requests.get()` calls between services don't carry trace
headers, so Jaeger would show disconnected single-span traces instead of one connected trace per
request).

## Goals

- Turn the 3-service skeleton into a fully instrumented, Docker-ready system satisfying the
  course's "Instrumentación Completa" requirements (métricas, structured logs, traces).
- Add the two bonus items in scope for this phase: real JWT auth, rate limiting on the Gateway.
- Make the services ready to be wired into Phase 2's Docker Compose stack (env-based service
  discovery, Dockerfiles, requirements.txt).

## Non-goals (deferred to later phases)

- Docker Compose / Prometheus / Grafana / Jaeger / Alertmanager configuration → Phase 2/3/4
- Security scanning tooling → Phase 5
- CI/CD wiring → Phase 6
- Kubernetes/Helm/Istio → Phase 7

## Architecture

Service split stays as defined in the instructions:

- **API Gateway** (port 5000) — entry point. Calls Auth Service to validate the inbound token,
  then calls Data Service, aggregates the response. Owns rate limiting.
- **Auth Service** (port 5001) — issues JWTs (`POST /login`) and validates them (`GET /validate`).
  Replaces the skeleton's random 90%-success simulation with real signature/expiry checks.
- **Data Service** (port 5002) — simulated DB query (`GET /data`), unchanged in shape from the
  skeleton.

All three expose `GET /metrics` (Prometheus exposition format) and `GET /health` (simple liveness
check, used later by Compose healthchecks and K8s probes).

### Request flow

```
Client → [Gateway] --validate--> [Auth]
                   --get data--> [Data]
       ← aggregated JSON response
```

Trace context and `request_id` propagate along every arrow above.

## Instrumentation

### Metrics (Prometheus client, per service, all on `/metrics`)

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `<svc>_requests_total` | Counter | `endpoint`, `status` | kept from skeleton |
| `<svc>_request_duration_seconds` | Histogram | — | kept from skeleton |
| `<svc>_active_connections` | Gauge | — | new; inc on request start, dec on response (in a `before_request`/`after_request` pair) |
| `<svc>_errors_total` | Counter | `error_type` | new; label = exception class name, incremented in the except block alongside the existing status-code counter |
| `gateway_throttled_total` | Counter | — | new; Gateway-only, incremented when rate limiter rejects a request |

### Logging

- Plain stdlib `logging`, but with a shared custom JSON `Formatter` (no extra dependency) defined
  once in `microservices/common/logging_config.py` and imported by all 3 services.
- Every log record includes: `timestamp`, `level`, `service`, `message`, `request_id`, `trace_id`
  (trace_id pulled from the current OTel span context if present, else `null`).
- `request_id`: Gateway generates a UUID4 if the inbound request has no `X-Request-ID` header,
  otherwise reuses it. Gateway forwards it as `X-Request-ID` on its calls to Auth and Data, so one
  user request produces log lines sharing the same `request_id` across all 3 services.

### Tracing

- `opentelemetry-sdk` + `opentelemetry-exporter-otlp` configured at startup in each service:
  a real `TracerProvider` with a `BatchSpanProcessor` exporting OTLP to Jaeger's OTLP endpoint
  (`JAEGER_OTLP_ENDPOINT` env var, defaults to `localhost:4317` for local dev, overridden to the
  Compose service name in Phase 2).
- `opentelemetry-instrumentation-requests` and `opentelemetry-instrumentation-flask` auto-instrument
  the outbound `requests` calls and inbound Flask routes, so trace context propagates over HTTP
  automatically (W3C `traceparent` header) — Gateway → Auth and Gateway → Data become children of
  the same trace instead of 3 disconnected single-span traces.
- Manual spans kept from the skeleton for clarity: `api-gateway-get-data` → `call-auth-service`,
  `call-data-service`; `auth-validate`; `data-service-query` → `database-query`. This satisfies the
  "at least 3 levels of spans" requirement.

## JWT Auth (Auth Service)

- `POST /login` — body `{"username": "demo", "password": "demo123"}` (hardcoded demo credential,
  this is a teaching project, not real user management). Returns `{"token": "<jwt>"}`.
- JWT: HS256, signed with `JWT_SECRET` env var (defaults to `dev-secret-change-me` if unset, so
  local `python` runs work out of the box; Phase 2/7 override it via Compose/K8s secrets), 15-minute
  expiry, claims `{sub: user_id, exp, iat}`.
- `GET /validate` — reads `Authorization: Bearer <token>` header (previously: no auth check at all,
  just a random coin flip). Verifies signature + expiry via `PyJWT`. Returns
  `{"valid": true, "user_id": ...}` on success, `{"valid": false, "error": "..."}` + 401 on failure
  (expired vs. invalid-signature distinguished in the error message, not in the HTTP status).
- Gateway forwards the client's `Authorization` header unchanged to `/validate`. If the client sent
  no token, Gateway short-circuits to 401 without calling Auth Service.

## Rate Limiting (API Gateway only)

- In-memory fixed-window limiter: 20 requests / 10 seconds per client IP (`request.remote_addr`).
  No Redis — single-instance scope for now, revisit if a later phase needs multi-instance Gateway.
- Implemented as a `before_request` hook maintaining a `dict[ip] -> (window_start, count)`.
- Over limit → `429 {"error": "rate limit exceeded"}`, increments `gateway_throttled_total`.

## Error Handling

- Existing try/except blocks kept. On exception: log structured error (with `request_id`/`trace_id`),
  increment both `<svc>_requests_total{status=500}` (existing) and `<svc>_errors_total{error_type=...}`
  (new), using the exception's class name as `error_type`.
- Auth/Data unreachable from Gateway (timeout, connection error) is handled the same way — the
  exception class name (`ConnectionError`, `Timeout`, etc.) becomes the `error_type` label, so
  Prometheus can distinguish network failures from application errors.

## Testing

- `pytest` + Flask test client, one test module per service under `microservices/tests/`.
- **Auth Service:** login issues a valid token; validate accepts a fresh valid token; validate
  rejects an expired token; validate rejects a tampered/invalid-signature token.
- **API Gateway:** rate limiter allows requests under the limit and rejects over the limit;
  aggregation logic returns 401 when Auth says invalid, returns combined data on success, returns
  500 with structured error when Data Service call raises — all with `requests` calls mocked
  (`responses` or `unittest.mock`), no real Auth/Data services required to run the tests.
- **Data Service:** `/data` returns the expected shape; metrics increment as expected.
- No Docker-dependent integration tests in this phase — those land naturally once Phase 2's Compose
  stack exists.

## Docker-readiness (for Phase 2, not built yet)

- Each service gets its own `Dockerfile` (`python:3.11-slim` base, non-root user, `requirements.txt`
  installed, `EXPOSE` the service port).
- Shared `microservices/requirements.txt`: `flask`, `requests`, `prometheus-client`, `pyjwt`,
  `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-flask`,
  `opentelemetry-instrumentation-requests`, `pytest`, `responses`.
- Inter-service URLs move to env vars: `AUTH_SERVICE_URL` (default `http://localhost:5001`),
  `DATA_SERVICE_URL` (default `http://localhost:5002`) — defaults work for local `python` runs,
  Phase 2 overrides them to Compose service names (`http://auth-service:5001`, etc.).
