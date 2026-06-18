# Phase 4: Grafana Dashboards — Design Spec

**Status:** Approved
**Date:** 2026-06-17
**Phase:** 4 of 8 (see Project Roadmap in `docs/superpowers/specs/2026-06-17-microservices-core-design.md`)

## Context

Phase 2 (observability stack) provisioned Grafana with Prometheus/Loki/Jaeger datasources and an
empty `observability/grafana/dashboards/` directory, ready for dashboard JSON with no provisioning
changes needed. Phase 3 (Prometheus rules & alerting) added 9 recording-rule series — 3 golden
signals (`service:request_rate:rate5m`, `service:error_ratio:rate5m`,
`service:request_latency_p95:5m`) × 3 services — each carrying a `service` label with values
`api-gateway`/`auth-service`/`data-service`, deliberately designed to make this phase's dashboards
simpler. This phase consumes both: dashboard JSON files dropped into the already-mounted
directory, querying both the new recording rules and the raw per-service metrics from Phase 1.

## Goals

- 4 dashboards: **Service Overview**, **Business Metrics**, **Security**, **Logs** (the course's
  Loki requirement — "dashboard with log panels" — gets its own dashboard rather than a row on
  Service Overview).
- Service Overview satisfies the course's explicit, graded requirements: Golden Signals (Latency,
  Traffic, Errors, Saturation), red/green status visual, a variable to filter by service, and at
  least 6 panels across different visualization types.
- One shared `$service` template variable, defined identically in all 4 dashboards, that filters
  every panel — Prometheus-backed (recording rules and raw metrics) and Loki-backed alike.
- Config-as-code only: new dashboard JSON files are the only changes. No edits to
  `observability/grafana/provisioning/`, no application code changes in `microservices/`.

## Non-goals (deferred to later phases)

- Implementing a security-scanning exporter that actually populates `security_vulnerabilities_total`
  / `security_score` → Phase 5. This phase only defines the metric names the Security dashboard
  queries; those two panels show "No data" until Phase 5 lands.
- CI/CD, Kubernetes/Helm/Istio → Phases 6–7.
- Any new Prometheus metrics, recording rules, or alerts — this phase only reads what Phases 1 and 3
  already expose.

## The `$service` variable

Defined once per dashboard (identical definition in all 4 JSON files):

```json
{
  "name": "service",
  "type": "query",
  "datasource": "Prometheus",
  "query": "label_values(up, job)",
  "includeAll": true,
  "multi": true,
  "current": { "text": "All", "value": "$__all" }
}
```

This resolves dynamically to `api-gateway`, `auth-service`, `data-service` — the literal Prometheus
`job` names from `observability/prometheus/prometheus.yml`. Three different label schemes all
happen to share these exact 3 strings, so one variable drives every panel with no name-mapping:

| Data source | Label carrying the service name | Why it matches |
|---|---|---|
| Phase 3 recording rules | `service` | Phase 3 set `labels: {service: "api-gateway"}` etc. by hand |
| Raw per-service metrics (`gateway_*`/`auth_*`/`data_*`) | `job` | Prometheus auto-attaches `job`/`instance` to every scraped sample; these metrics have no app-defined `service` label, so `job` is the only way to filter them by service |
| Loki log lines | `container` | `docker-compose.yml` sets explicit `container_name: api-gateway` etc. (Phase 2), so Promtail's `container` relabel (Phase 2) emits the same 3 strings, not Compose's default `<project>-<service>-<n>` naming |

Panel queries therefore use `{service=~"$service"}` against recording rules, `{job=~"$service"}`
against raw metrics, and `{container=~"$service"}` against Loki — three different label names, one
variable, no metric-name string templating.

## Dashboard 1: Service Overview

| # | Panel | Type | Query | Notes |
|---|---|---|---|---|
| 1 | Request Rate | Time series | `service:request_rate:rate5m{service=~"$service"}` | Golden signal: Traffic |
| 2 | Error Rate % | Stat | `service:error_ratio:rate5m{service=~"$service"} * 100` | Golden signal: Errors. Thresholds green `<1`, red `≥1`, matching the `HighErrorRate` alert |
| 3 | Latency p95 | Gauge | `service:request_latency_p95:5m{service=~"$service"}` | Golden signal: Latency. Thresholds green `<0.5`, red `≥0.5`, matching `HighLatency` |
| 4 | Service Status | Stat, value-mapped | `up{job=~"$service"}` | Red/green visual: `1`→UP (green), `0`→DOWN (red) |
| 5 | Saturation | Time series | `sum by (job) ({__name__=~".*_active_connections", job=~"$service"})` | Golden signal: Saturation, from each service's `active_connections` gauge |
| 6 | Top Errors | Bar chart | `sum by (job, error_type) (increase({__name__=~".*_errors_total", job=~"$service"}[$__range]))` | Breaks down `*_errors_total{error_type}` |
| 7 | Request Duration | Heatmap | `sum(rate({__name__=~".*_request_duration_seconds_bucket", job=~"$service"}[5m])) by (le)` | From each service's duration histogram buckets |

7 panels across 5 visualization types (time series, stat, gauge, bar chart, heatmap) — covers all 4
Golden Signals, the red/green requirement, and the course's 6 named panel types in one dashboard.

## Dashboard 2: Business Metrics

Built entirely from metrics that already exist (Phase 1), reframed as business signals — no new
instrumentation, no `microservices/` changes, per the explicit choice to keep this phase inside
`observability/grafana/`'s file scope.

| Panel | Type | Business framing | Query |
|---|---|---|---|
| Active Users | Time series | login activity as a user-engagement proxy | `rate(auth_requests_total{endpoint="/login",status="200"}[5m])` |
| Login Success Rate | Stat | conversion-style health metric | `sum(rate(auth_requests_total{endpoint="/login",status="200"}[5m])) / sum(rate(auth_requests_total{endpoint="/login"}[5m])) * 100` |
| Data Items Served | Stat | business throughput (each `/data` response carries 3 items) | `sum(rate(data_requests_total{endpoint="/data",status="200"}[5m])) * 3` |
| API Usage by Endpoint | Pie chart | feature-usage breakdown | `sum by (endpoint) (increase(gateway_requests_total[$__range]))` |
| Throttled Requests | Time series | demand/capacity signal | `rate(gateway_throttled_total[5m])` |

`$service` filtering applies where the metric carries a `job` label (Active Users, Login Success
Rate); Data Items Served and API Usage by Endpoint are inherently single-service (data-service,
api-gateway respectively) so the variable has no effect on them — documented in-dashboard via panel
descriptions, not hidden.

## Dashboard 3: Security

| Panel | Type | Data status | Query |
|---|---|---|---|
| Failed Auth Attempts | Time series | live today | `sum(rate(auth_requests_total{endpoint=~"/login\|/validate",status="401"}[5m]))` |
| Auth Error Breakdown | Bar chart | live today | `sum by (error_type) (increase(auth_errors_total[$__range]))` |
| Rate Limit Triggers | Time series | live today | `rate(gateway_throttled_total[5m])` |
| CVEs Detected | Stat/table by severity | **no data until Phase 5** | `sum by (severity) (security_vulnerabilities_total)` |
| Security Score | Gauge (0–100) | **no data until Phase 5** | `security_score` |

The last two panels query metric names that don't exist yet — this is the metric-naming contract
Phase 5's security-scanning exporter needs to satisfy (e.g. via a Pushgateway or node_exporter
textfile collector publishing `security_vulnerabilities_total{severity="HIGH|CRITICAL|..."}` and a
single `security_score` gauge). They'll render "No data" until then, by design, not by oversight.

## Dashboard 4: Logs

| Panel | Type | Query |
|---|---|---|
| Log Volume by Service | Time series | `sum by (container) (count_over_time({container=~"$service"}[$__interval]))` |
| Errors & Warnings | Logs panel | `{container=~"$service"} \| json \| level=~"ERROR\|WARNING"` |
| Live Tail | Logs panel | `{container=~"$service"}` |

Relies on Phase 1's structured JSON logging (`level` field present on every log line) and Phase 2's
Promtail `container` label — no Loki/Promtail config changes needed.

## File layout

```
observability/grafana/dashboards/
├── service-overview.json   # NEW
├── business-metrics.json   # NEW
├── security.json           # NEW
└── logs.json                # NEW
```

No changes to `observability/grafana/provisioning/dashboards/dashboards.yml` — it already points
its file provider at this directory with `folder: ''` (Phase 2), so any JSON dropped in here is
picked up automatically once Grafana reloads (or restarts).

### Why these specific choices

- **Hand-authored JSON, not a generator (Jsonnet/Grafonnet or a custom script).** Every prior phase
  in this project hand-writes its config (Prometheus rules, Alertmanager YAML) with no build step;
  a generator would be the first tool in the stack that needs a regeneration step to stay in sync,
  for a one-time deliverable (the course explicitly asks for "JSON export de dashboards" as a final
  artifact, not a build pipeline). Rejected as disproportionate for 4 dashboards.
- **One variable definition reused verbatim across 4 files, not 4 different filtering schemes.**
  Considered making Business Metrics' single-service panels variable-free entirely (since the
  variable has no effect on them), but keeping the same `$service` variable present in every
  dashboard — even where some panels ignore it — keeps the UX consistent (the filter dropdown is
  always in the same place) at the cost of 2 panels per Business Metrics dashboard not actually
  responding to it (documented via panel description, not a functional gap).
- **Security dashboard ships now with 2 "no data" panels rather than deferring the whole dashboard
  to Phase 5.** Chosen so Phase 4 delivers all 3 dashboards the course names explicitly, and so
  Phase 5 inherits a concrete metric-naming contract instead of having to design the Grafana side
  itself. The cost: a freshly-provisioned Grafana shows 2 empty panels until Phase 5 is implemented.
- **Logs gets its own dashboard instead of a row on Service Overview.** The course separates the
  Loki requirement ("dashboard con panels de logs") from the Grafana dashboard list (Service
  Overview / Business Metrics / Security); a dedicated dashboard matches that separation and keeps
  Service Overview's 7 panels focused on metrics rather than mixing in log panels with a different
  query language and refresh behavior.

## Testing / Verification (for the implementation plan)

1. Validate each dashboard JSON is well-formed (`python3 -m json.tool <file> > /dev/null` per file)
   before mounting.
2. Bring up the stack (`docker compose up -d`, already running from Phase 3's verification or
   restarted fresh) and confirm Grafana's dashboard list shows all 4 new dashboards.
3. Generate traffic (`auth-service:5001/login` then a handful of `api-gateway:5000/api/data` calls,
   same pattern as Phase 3's verification) so Service Overview's and Business Metrics' panels have
   non-empty data to render.
4. Open each dashboard and confirm: the `$service` variable populates with `api-gateway`,
   `auth-service`, `data-service` (+ All); switching it changes the data shown in at least one
   panel per dashboard; no panel shows a query error (red "!" icon) — "No data" is acceptable only
   for the Security dashboard's CVE/score panels.
5. Stop one service (`docker compose stop data-service`) and confirm Service Overview's Service
   Status panel turns red for that service while the others stay green.
6. Confirm the Logs dashboard's Live Tail panel shows real log lines and the Errors & Warnings panel
   correctly filters to `level=~"ERROR|WARNING"` only.

## Known Limitations (Accepted for This Phase's Scope)

- **Security dashboard's CVE/score panels show "No data" until Phase 5** is implemented against the
  metric-naming contract defined here (`security_vulnerabilities_total{severity}`, `security_score`).
- **Business Metrics dashboard reuses existing technical metrics under a business framing rather
  than introducing real domain metrics** (no signups/revenue exist in this project) — by explicit
  choice, to avoid touching `microservices/` files in a phase scoped to `observability/grafana/`.
- **Two Business Metrics panels (Data Items Served, API Usage by Endpoint) don't respond to the
  `$service` variable** since their underlying metrics are inherently single-service — the variable
  is still present in the dashboard for UX consistency, just inert for those two panels.
- **No alert list / annotations panel.** Dashboards don't surface Phase 3's firing alerts visually
  (e.g. a Grafana "Alert list" panel reading Alertmanager) — out of scope; alerts are already
  visible via Prometheus's `/alerts` and Alertmanager's UI per Phase 3's verification steps.
