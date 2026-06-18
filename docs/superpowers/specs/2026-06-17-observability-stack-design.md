# Phase 2: Observability Stack — Design Spec

**Status:** Approved
**Date:** 2026-06-17
**Phase:** 2 of 8 (see Project Roadmap in `docs/superpowers/specs/2026-06-17-microservices-core-design.md`)

## Context

Phase 1 (microservices core) is complete: `api_gateway.py`, `auth_service.py`, `data_service.py` are
fully instrumented (Prometheus metrics, structured JSON logs, OTel tracing, real JWT auth, rate
limiting) and each has its own Dockerfile (`microservices/Dockerfile.{api-gateway,auth-service,data-service}`),
verified to build and serve `/health` standalone.

This phase turns that into a runnable system: one Docker Compose stack that builds and runs the 3
microservices alongside Prometheus, Grafana, Loki+Promtail, Jaeger, and Alertmanager, all wired
together on one network.

## Goals

- A single `docker-compose up` brings up all 3 microservices + 6 observability containers, fully
  networked, with the microservices' existing metrics/logs/traces actually flowing into
  Prometheus/Loki/Jaeger.
- Config-as-code for everything: Prometheus scrape config, Grafana datasources, Loki/Promtail
  config, Alertmanager stub config — all checked into git, none clicked together in a UI.
- Leave clean extension points for later phases so they don't need to touch this phase's files:
  an empty Prometheus rules directory for Phase 3, an empty Grafana dashboards directory for
  Phase 4.

## Non-goals (deferred to later phases)

- Recording rules, alert rules, Alertmanager→Slack routing → Phase 3 (this phase: Alertmanager
  container + minimal no-op config only, Prometheus already pointed at it)
- Grafana dashboards (Service Overview, Business Metrics, Security) → Phase 4 (this phase:
  datasource provisioning only)
- Security scanning, CI/CD, Kubernetes/Helm/Istio → Phases 5–7

## Architecture

```
                         ┌──────────────── observability-net (bridge) ────────────────┐
                         │                                                              │
  client ──▶ api-gateway:5000 ──validate──▶ auth-service:5001                          │
                  │      └──────get data───▶ data-service:5002                         │
                  │                                                                      │
                  ├──scrape /metrics──────▶ prometheus:9090 ──alerts──▶ alertmanager:9093│
                  ├──OTLP gRPC :4317──────▶ jaeger:16686 (+ badger volume)               │
                  └──stdout JSON logs─────▶ promtail ──push──▶ loki:3100                │
                                                                    ▲                     │
                                                    grafana:3000 ───┘ (+ prometheus, jaeger datasources)
                         └──────────────────────────────────────────────────────────────┘
```

All 9 containers share one Docker bridge network. Promtail discovers the 3 microservice
containers via Docker service discovery (mounted `/var/run/docker.sock`, read-only) and tails
their JSON stdout — no logging-driver or Dockerfile changes needed.

### Request/telemetry flow

- **Metrics:** each service already exposes `/metrics`; Prometheus scrapes all three plus itself
  on a fixed interval.
- **Logs:** each service already logs structured JSON to stdout; Promtail tails Docker's
  container log files (discovered via the Docker socket), labels each line with the container
  name, and pushes to Loki.
- **Traces:** each service already exports OTLP spans via `JAEGER_OTLP_ENDPOINT`; in Compose this
  resolves to `jaeger:4317` instead of the `localhost:4317` dev default.

## File layout

```
docker-compose.yml                                  # root: the full stack
observability/
├── prometheus/
│   ├── prometheus.yml             # scrape configs (gateway/auth/data/self) + alerting: → alertmanager:9093
│   └── rules/.gitkeep             # empty; Phase 3 drops *.yml rule files here, no prometheus.yml edit needed
├── alertmanager/
│   └── alertmanager.yml           # one "default" receiver, no integrations; Phase 3 replaces with Slack routing
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasources.yml   # Prometheus, Loki, Jaeger
│   │   └── dashboards/dashboards.yml     # provider config pointing at ../../dashboards
│   └── dashboards/.gitkeep        # empty; Phase 4 drops dashboard JSON here, no provisioning edit needed
├── loki/
│   └── loki-config.yml            # single-binary mode, filesystem chunk + index storage
└── promtail/
    └── promtail-config.yml        # docker_sd_configs, relabel container name, push to loki:3100
```

No Dockerfiles are added in this phase. The 3 microservices reuse their existing
`microservices/Dockerfile.{api-gateway,auth-service,data-service}` as build contexts; the 6
observability tools run from official upstream images with config mounted in as volumes — no
custom images needed for any of them.

## Components

| Service | Image | Port(s) exposed to host | Volume | Depends on |
|---|---|---|---|---|
| api-gateway | build: `microservices/Dockerfile.api-gateway` | 5000 | — | auth-service (healthy), data-service (healthy) |
| auth-service | build: `microservices/Dockerfile.auth-service` | 5001 | — | — |
| data-service | build: `microservices/Dockerfile.data-service` | 5002 | — | — |
| prometheus | `prom/prometheus` | 9090 | `prometheus_data` | alertmanager (started) |
| grafana | `grafana/grafana` | 3000 | `grafana_data` | prometheus (healthy), loki (healthy), jaeger (started) |
| loki | `grafana/loki` | 3100 | `loki_data` | — |
| promtail | `grafana/promtail` | — | — (reads docker socket + log dirs, read-only) | loki (started) |
| jaeger | `jaegertracing/all-in-one` | 16686 (UI), 4317 (OTLP gRPC) | `jaeger_data` (Badger) | — |
| alertmanager | `prom/alertmanager` | 9093 | `alertmanager_data` | — |

Exact image tags are pinned to specific stable versions during implementation (verified pullable
at that time, not hardcoded speculatively in this spec).

### Why these specific config choices

- **Jaeger storage = Badger, not in-memory default.** Badger is an embedded persistent
  key-value store built into the `jaegertracing/all-in-one` image — enabling it is two env vars
  (`SPAN_STORAGE_TYPE=badger`, `BADGER_EPHEMERAL=false`) plus one volume, no extra container. Keeps
  Jaeger consistent with every other component persisting across `docker-compose down`/`up`.
- **Promtail via Docker service discovery**, not a custom logging driver. Standard pattern for
  Compose: mount `/var/run/docker.sock` (to discover running containers) and
  `/var/lib/docker/containers` (to read their JSON log files) read-only into Promtail, configure
  `docker_sd_configs` in `promtail-config.yml`. No changes to how the microservices log (they
  already log structured JSON to stdout).
- **Alertmanager gets a real (if minimal) config now**, not a deferred container. Prometheus's
  `alerting:` block needs a live target to talk to even with zero rules defined; standing up the
  container with a single no-op `default` receiver now means Phase 3 only edits
  `alertmanager.yml`'s receiver/route content, not the wiring.
- **Grafana provisioning is split into datasources (this phase) vs. dashboards (Phase 4)** via two
  separate provisioning YAML files, so Phase 4 only adds dashboard JSON under
  `observability/grafana/dashboards/` without touching this phase's files.
- **Healthchecks** are defined inline in `docker-compose.yml` (not baked into the Dockerfiles):
  the 3 microservices use a `python -c "urllib.request.urlopen(...)"` check against `/health`
  (the base image already has Python, no extra tooling needed); Prometheus/Grafana/Loki use
  `wget --spider` against their respective health endpoints (their images include `wget`).
  Jaeger/Alertmanager/Promtail images lack shell tooling for that, so those three rely on
  plain Compose startup-order `depends_on` (service started, not health-gated).
- **No hard `depends_on` from Prometheus to the 3 microservices.** Prometheus scrapes on an
  interval and just shows a target as `down` until it's reachable — no need to gate its startup
  on the services being ready.

## Environment variables (set in `docker-compose.yml`)

| Var | Set on | Value |
|---|---|---|
| `AUTH_SERVICE_URL` | api-gateway | `http://auth-service:5001` |
| `DATA_SERVICE_URL` | api-gateway | `http://data-service:5002` |
| `JAEGER_OTLP_ENDPOINT` | all 3 microservices | `jaeger:4317` |

`JWT_SECRET` is left unset on `auth-service`, so it falls back to the existing
`dev-secret-change-me` code default — fine for this teaching project, no secret to manage in
Compose.

## Persistence

Named volumes for `prometheus_data`, `grafana_data`, `loki_data`, `alertmanager_data`, and
`jaeger_data` (Badger). Data survives `docker-compose down`; `docker-compose down -v` gives a full
clean slate. This mirrors (at small scale) the production pattern of persisting runtime data on
durable storage while keeping all configuration as code in git — the actual durability/redundancy
layer (S3, remote-write, managed services) is out of scope for a single-host teaching stack.

## Testing / Verification (for the implementation plan)

No Docker-dependent automated tests are added in this phase — verification is manual, run during
implementation:

1. `docker-compose config` — validates Compose file syntax before attempting to build/run.
2. Bring up the 6 observability containers and confirm each responds: Prometheus `/-/healthy`,
   Grafana `/api/health`, Loki `/ready`, Jaeger UI on 16686, Alertmanager `/-/healthy`.
3. Bring up the full stack (including the 3 microservices) and confirm `docker-compose ps` shows
   all 9 containers healthy/running.
4. Query Prometheus's targets API and confirm all 3 microservices show as `up`.
5. Generate a few requests through `api-gateway:5000/api/data` (after logging in via
   `auth-service:5001/login`) and confirm: a corresponding trace with 3+ span levels appears in
   the Jaeger UI; log lines for that request are queryable in Loki via
   `{container=~"api-gateway|auth-service|data-service"}` and share a `request_id`.
6. Confirm Grafana's Prometheus/Loki/Jaeger datasources show as connected via Grafana's
   provisioning (no manual datasource setup needed).
