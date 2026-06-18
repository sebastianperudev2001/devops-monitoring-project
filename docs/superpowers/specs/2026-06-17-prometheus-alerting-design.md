# Phase 3: Prometheus Rules & Alerting — Design Spec

**Status:** Approved
**Date:** 2026-06-17
**Phase:** 3 of 8 (see Project Roadmap in `docs/superpowers/specs/2026-06-17-microservices-core-design.md`)

## Context

Phase 2 (observability stack) is complete: Prometheus already scrapes the 3 microservices and points
its `alerting:` block at a live Alertmanager container, but Prometheus's `rules/` directory is empty
(`.gitkeep` only) and Alertmanager's config is a single no-op `default` receiver. This phase fills in
both: recording rules + alert rules for Prometheus, and a real Slack-routed receiver for Alertmanager.
No other phase's files are touched.

## Goals

- At least 3 recording rules and at least 5 alerts (course minimums), evaluated by the Prometheus
  container already running.
- Alerts cover all 3 services (api-gateway, auth-service, data-service), not just api-gateway, by
  generalizing on a `service` label rather than hardcoding one service's metric names per alert.
- Alertmanager routes every alert to a Slack receiver, configured so the webhook is not hardcoded into
  committed config.
- Config-as-code only: new rule files and the updated Alertmanager config are the only changes; no
  edits to `prometheus.yml` or `docker-compose.yml` are needed (Phase 2 already wired `rule_files` and
  the Alertmanager target).

## Non-goals (deferred to later phases)

- Grafana dashboards consuming these rules (Service Overview, Business Metrics, Security) → Phase 4.
  This phase's recording rules are deliberately named/labeled to make those dashboards simpler
  (one `service` label to filter on instead of 3 differently-prefixed metric families per panel), but
  no dashboard JSON is added here.
- True container-level CPU/memory metrics (cAdvisor or similar) — out of scope by explicit choice; see
  "Why these specific config choices" below.
- Security scanning, CI/CD, Kubernetes/Helm/Istio → Phases 5–7.

## Recording rules

New file: `observability/prometheus/rules/recording-rules.yml`, one rule group `service_golden_signals`.
Each of the 3 metric names below has one rule entry per service (9 entries total), each entry adding a
`labels: {service: "<name>"}` block so all 3 services' samples share one metric name and one label to
filter by:

| Recording rule | Golden signal | Expression (per service, `<svc>` = `gateway`/`auth`/`data` metric prefix) |
|---|---|---|
| `service:request_rate:rate5m` | Traffic | `sum(rate(<svc>_requests_total[5m]))` |
| `service:error_ratio:rate5m` | Errors | `sum(rate(<svc>_requests_total{status=~"5.."}[5m])) / sum(rate(<svc>_requests_total[5m]))` |
| `service:request_latency_p95:5m` | Latency | `histogram_quantile(0.95, sum(rate(<svc>_request_duration_seconds_bucket[5m])) by (le))` |

`<svc>_requests_total` / `<svc>_request_duration_seconds_bucket` map to the metrics already exposed by
each service: `gateway_requests_total`/`gateway_request_duration_seconds_bucket` (api-gateway),
`auth_requests_total`/`auth_request_duration_seconds_bucket` (auth-service),
`data_requests_total`/`data_request_duration_seconds_bucket` (data-service) — defined in
`microservices/api_gateway.py`, `microservices/auth_service.py`, `microservices/data_service.py`
respectively (Phase 1, unchanged by this phase).

## Alert rules

New file: `observability/prometheus/rules/alert-rules.yml`, one rule group `microservices_alerts`.
6 alerts cover the 5 course-required categories (CPU and Memory split into two alerts for clearer
routing/runbooks, since they have distinct causes and thresholds):

| Alert | Expr | For | Severity |
|---|---|---|---|
| HighErrorRate | `service:error_ratio:rate5m > 0.01` | 5m | critical |
| HighLatency | `service:request_latency_p95:5m > 0.5` | 5m | warning |
| ServiceDown | `label_replace(up{job=~"api-gateway\|auth-service\|data-service"}, "service", "$1", "job", "(.+)") == 0` | 1m | critical |
| LowThroughput | `service:request_rate:rate5m < 0.1667` | 5m | warning |
| HighCPUUsage | `label_replace(rate(process_cpu_seconds_total{job=~"api-gateway\|auth-service\|data-service"}[5m]), "service", "$1", "job", "(.+)") > 0.8` | 5m | warning |
| HighMemoryUsage | `label_replace(process_resident_memory_bytes{job=~"api-gateway\|auth-service\|data-service"}, "service", "$1", "job", "(.+)") > 3e8` | 5m | warning |

`0.1667` = 10 req/min expressed as req/sec (course states the threshold in req/min; Prometheus rate
vectors are per-second). `3e8` = 300MB, a reasonable ceiling for a small Flask process with no
meaningful working set, chosen because the project has no existing Docker memory limit to alert
against a percentage of (see below). Every alert carries a `service` label (either natively from the
recording rules, or attached via `label_replace` from `job` for the 3 alerts on raw metrics) so
Alertmanager grouping and any future Grafana alert list panel can filter/group on one consistent label
name regardless of which alert fired. `summary`/`description` annotations on each alert template in
`{{ $labels.service }}` and `{{ $value }}`.

### Why these specific config choices

- **Recording rules generalize across all 3 services, alert rules don't duplicate per-service.**
  Rather than writing `HighErrorRateGateway`, `HighErrorRateAuth`, `HighErrorRateData` (3x the rules,
  3x the Alertmanager routing surface), each alert is written once against a recording rule that
  already has one entry per service. A problem isolated to auth-service or data-service alone fires
  the same alert as one in api-gateway, distinguished only by the `service` label — this is the
  standard Prometheus pattern for multi-service alerting and keeps the alert file's line count
  proportional to alert *types*, not services × types.
- **CPU/Memory alerts use the services' own process self-metrics
  (`process_cpu_seconds_total`/`process_resident_memory_bytes`), not cAdvisor.** These come free from
  `prometheus_client`'s default `ProcessCollector` — already scraped today via each service's
  `/metrics`, zero code or infra changes. The trade-off, accepted explicitly: these only see the
  Python process's own usage, not a Docker-level view, so thresholds are absolute guesses rather than
  "% of configured container limit" (no CPU/memory limits are set on any service in
  `docker-compose.yml` today, so there's nothing to compute a percentage against regardless). A
  cAdvisor-based alternative (true cgroup metrics, percentage-of-limit alerting) was considered and
  rejected for this phase to avoid adding a 10th container, a new scrape job, and
  `/var/run/docker.sock` + `/sys/fs/cgroup` mounts — disproportionate for a teaching project's "high
  CPU/memory" checkbox. Worth reconsidering if this stack ever needs to alert on actual resource
  exhaustion rather than a runaway/leaking process.
- **Alertmanager's Slack webhook is injected via `api_url_file`, not env-var expansion.** The
  original plan assumed Alertmanager supported `--config.expand-env` (as Prometheus does for
  `--enable-feature=expand-external-labels`); verified via search that Alertmanager has no such flag —
  environment variable substitution in its config file is an open, unimplemented feature request
  (prometheus/alertmanager#2818). `slack_configs[].api_url_file` is the actual, documented, natively
  supported mechanism (available well before our pinned `v0.27.0`) for keeping a webhook URL out of
  committed YAML: it's a file path, resolved at runtime, instead of an inline value. This preserves the
  originally-wanted outcome — a committed placeholder, swapped for a real value locally without
  touching tracked config — through Alertmanager's actual supported feature rather than one it lacks.
- **LowThroughput is expected to fire on an idle stack.** With nothing generating traffic,
  `service:request_rate:rate5m` is `0 < 0.1667` by definition. This is correct alerting behavior for a
  "low throughput" signal, not a bug — the course's `traffic-gen.sh` (Phase ref, run manually during
  demos) is what keeps it from firing during verification.
- **No changes to `prometheus.yml` or `docker-compose.yml`.** Phase 2 already configured
  `rule_files: [/etc/prometheus/rules/*.yml]` and pointed `alerting:` at `alertmanager:9093` — dropping
  new `*.yml` files into the already-mounted `observability/prometheus/rules/` directory and editing
  the already-mounted `observability/alertmanager/alertmanager.yml` is sufficient; both containers
  pick up changes on restart (`docker-compose restart prometheus alertmanager`), no rebuild needed.

## File layout

```
observability/
├── prometheus/
│   └── rules/
│       ├── recording-rules.yml   # NEW — 3 golden-signal recording rules × 3 services
│       └── alert-rules.yml       # NEW — 6 alerts (5 required categories, CPU/Memory split)
└── alertmanager/
    ├── alertmanager.yml          # MODIFIED — real route + slack_configs receiver (api_url_file)
    └── secrets/
        └── slack_webhook_url     # NEW, tracked with a placeholder — see below
```

`observability/alertmanager/secrets/slack_webhook_url` is a plain-text file containing one line,
committed with the placeholder `https://hooks.slack.com/services/REPLACE/ME/PLACEHOLDER`. It's bind-
mounted read-only into the Alertmanager container at `/etc/alertmanager/secrets/slack_webhook_url`
(new volume line in `docker-compose.yml`'s `alertmanager` service — the one `docker-compose.yml` touch
this phase needs, since Phase 2 didn't mount a secrets path). To get live Slack delivery, replace the
file's contents locally with a real incoming-webhook URL and restart the `alertmanager` container; this
project has no secrets-management layer (consistent with `JWT_SECRET`'s code-default fallback from
Phase 1), so anyone doing this should be careful not to commit their real URL over the placeholder.

### Alertmanager routing

```yaml
route:
  receiver: slack-notifications
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: slack-notifications
    slack_configs:
      - api_url_file: /etc/alertmanager/secrets/slack_webhook_url
        channel: '#alerts'
        send_resolved: true
        title: '{{ .CommonLabels.alertname }}'
        text: "{{ range .Alerts }}{{ .Annotations.description }}\n{{ end }}"
```

`text` is double-quoted, not single-quoted: YAML's single-quoted style never processes backslash escapes, so a single-quoted `\n` would render as the literal characters `\`+`n` in the Slack message rather than a line break between grouped alerts (caught in code review during implementation).

One receiver for all alerts (no severity-based routing tree) — proportionate for 6 alerts in a teaching
project; a real deployment would likely split `critical`→pager, `warning`→Slack.

## Testing / Verification (for the implementation plan)

1. `promtool check rules observability/prometheus/rules/recording-rules.yml
   observability/prometheus/rules/alert-rules.yml` — validates syntax before touching the running stack.
2. `docker-compose restart prometheus alertmanager` (stack already up from Phase 2) and confirm via
   Prometheus's `/api/v1/rules` that both rule groups loaded with zero `evaluationTime` errors.
3. Confirm the 9 recording rule series appear in Prometheus's `/graph` (e.g.
   `service:request_rate:rate5m`) once scraping has run for 5+ minutes.
4. Force `ServiceDown`: stop one microservice container (`docker-compose stop auth-service`), wait >1m,
   confirm the alert transitions `pending` → `firing` in Prometheus's `/alerts` and appears in
   Alertmanager's `/#/alerts`.
5. Check Alertmanager's logs for a Slack POST attempt for that firing alert (it will fail against the
   placeholder URL — confirms the routing/receiver wiring is correct independent of real delivery).
6. Restart the stopped service and confirm the alert resolves (`firing` disappears, and if a real
   webhook were configured, `send_resolved: true` would post a resolution message).

## Known Limitations (Accepted for This Phase's Scope)

- **CPU/Memory alerts measure process self-reported usage, not container limits** (see "Why these
  specific config choices"). Thresholds (80% of one core, 300MB RSS) are reasonable guesses for this
  project's small Flask services, not derived from any configured resource ceiling.
- **LowThroughput fires by design whenever the stack is idle.** Expected, not a defect — run the
  course's traffic generator to keep it quiet during a demo.
- **Slack delivery is unverified end-to-end in this phase** without a real webhook URL in
  `observability/alertmanager/secrets/slack_webhook_url`; verification (step 5 above) confirms correct
  config/routing, not actual message delivery.
- **One flat Alertmanager route for all severities.** No `critical` vs `warning` differentiation in
  routing (e.g. paging vs. Slack-only) — proportionate for 6 alerts in a teaching stack, would need
  revisiting for a real on-call setup.
