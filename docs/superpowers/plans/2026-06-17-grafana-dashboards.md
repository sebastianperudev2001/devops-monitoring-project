# Grafana Dashboards (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 Grafana dashboards (Service Overview, Business Metrics, Security, Logs) as provisioned JSON files, per `docs/superpowers/specs/2026-06-17-grafana-dashboards-design.md`.

**Architecture:** 4 standalone dashboard JSON files dropped into the already-provisioned `observability/grafana/dashboards/` directory — no provisioning or app-code changes. Every dashboard defines the same `$service` template variable (`label_values(up, job)` against Prometheus), which filters Prometheus panels via `service`/`job` labels and Loki panels via the `container` label — all 3 happen to share the same 3 string values (`api-gateway`/`auth-service`/`data-service`).

**Tech Stack:** Grafana 11.2.0 dashboard JSON model (`schemaVersion: 39`), querying Prometheus (PromQL, including Phase 3's recording rules) and Loki (LogQL) datasources already provisioned by Phase 2.

## Global Constraints

- Datasources are referenced by name (`"datasource": "Prometheus"` / `"datasource": "Loki"`), not by UID — `observability/grafana/provisioning/datasources/datasources.yml` sets no explicit `uid:`, and this phase must not edit anything under `observability/grafana/provisioning/`.
- The `$service` variable must be defined identically in all 4 dashboards: `type: query`, `datasource: Prometheus`, `query: label_values(up, job)`, `includeAll: true`, `multi: true`.
- No changes to `microservices/` — no new metrics, no new instrumentation.
- New files land only under `observability/grafana/dashboards/`.
- The Security dashboard's `CVEs Detected` and `Security Score` panels query `security_vulnerabilities_total{severity}` and `security_score` — metric names that don't exist yet (Phase 5 will populate them). They are expected to show "No data" until then; this is not a bug to fix in this phase.

---

## File Structure

```
observability/grafana/dashboards/
├── service-overview.json   # NEW — Task 1
├── business-metrics.json   # NEW — Task 2
├── security.json           # NEW — Task 3
└── logs.json                # NEW — Task 4
```

No other files change. Task 5 brings up the stack and verifies all 4 dashboards end-to-end.

---

### Task 1: Service Overview dashboard

**Files:**
- Create: `observability/grafana/dashboards/service-overview.json`

**Interfaces:**
- Consumes: Phase 3 recording rules (`service:request_rate:rate5m`, `service:error_ratio:rate5m`, `service:request_latency_p95:5m`, each labeled `service`); Phase 1 raw metrics (`gateway_active_connections`/`auth_active_connections`/`data_active_connections`, `gateway_errors_total`/`auth_errors_total`/`data_errors_total`{`error_type`}, `*_request_duration_seconds_bucket`); Prometheus's auto-attached `up{job}`.
- Produces: nothing consumed by other tasks (dashboards are independent).

- [ ] **Step 1: Write `observability/grafana/dashboards/service-overview.json`**

```json
{
  "title": "Service Overview",
  "uid": "service-overview",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "graphTooltip": 1,
  "style": "dark",
  "timezone": "browser",
  "tags": ["microservices", "golden-signals"],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "10s",
  "templating": {
    "list": [
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(up, job)",
        "includeAll": true,
        "multi": true,
        "current": { "text": "All", "value": "$__all" },
        "refresh": 2,
        "sort": 1
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "Request Rate",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "service:request_rate:rate5m{service=~\"$service\"}",
          "legendFormat": "{{service}}"
        }
      ]
    },
    {
      "id": 2,
      "title": "Service Status",
      "type": "stat",
      "datasource": "Prometheus",
      "gridPos": { "x": 12, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": { "text": "DOWN", "color": "red" },
                "1": { "text": "UP", "color": "green" }
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "red", "value": null },
              { "color": "green", "value": 1 }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "background",
        "textMode": "value_and_name"
      },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "up{job=~\"$service\"}",
          "legendFormat": "{{job}}"
        }
      ]
    },
    {
      "id": 3,
      "title": "Error Rate %",
      "type": "stat",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 1 }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": { "calcs": ["lastNotNull"] },
        "colorMode": "value",
        "textMode": "value_and_name"
      },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "service:error_ratio:rate5m{service=~\"$service\"} * 100",
          "legendFormat": "{{service}}"
        }
      ]
    },
    {
      "id": 4,
      "title": "Latency p95",
      "type": "gauge",
      "datasource": "Prometheus",
      "gridPos": { "x": 8, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "min": 0,
          "max": 2,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 0.5 }
            ]
          }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] } },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "service:request_latency_p95:5m{service=~\"$service\"}",
          "legendFormat": "{{service}}"
        }
      ]
    },
    {
      "id": 5,
      "title": "Saturation (Active Connections)",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 16, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum by (job) ({__name__=~\".*_active_connections\", job=~\"$service\"})",
          "legendFormat": "{{job}}"
        }
      ]
    },
    {
      "id": 6,
      "title": "Top Errors",
      "type": "barchart",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 16, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum by (job, error_type) (increase({__name__=~\".*_errors_total\", job=~\"$service\"}[$__range]))",
          "legendFormat": "{{job}} - {{error_type}}"
        }
      ]
    },
    {
      "id": 7,
      "title": "Request Duration Heatmap",
      "type": "heatmap",
      "datasource": "Prometheus",
      "gridPos": { "x": 12, "y": 16, "w": 12, "h": 8 },
      "options": { "calculate": false, "yAxis": { "unit": "s" } },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum(rate({__name__=~\".*_request_duration_seconds_bucket\", job=~\"$service\"}[5m])) by (le)",
          "format": "heatmap",
          "legendFormat": "{{le}}"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax and structure**

Run:
```bash
python3 -c "
import json
d = json.load(open('observability/grafana/dashboards/service-overview.json'))
assert d['title'] == 'Service Overview'
assert d['uid'] == 'service-overview'
assert len(d['panels']) == 7
assert any(v['name'] == 'service' for v in d['templating']['list'])
print('OK: 7 panels, service variable present')
"
```
Expected: `OK: 7 panels, service variable present`

- [ ] **Step 3: Commit**

```bash
git add observability/grafana/dashboards/service-overview.json
git commit -m "feat: add Grafana Service Overview dashboard"
```

---

### Task 2: Business Metrics dashboard

**Files:**
- Create: `observability/grafana/dashboards/business-metrics.json`

**Interfaces:**
- Consumes: `auth_requests_total{endpoint,status,job}`, `data_requests_total{endpoint,status}`, `gateway_requests_total{endpoint,status}`, `gateway_throttled_total` (all Phase 1, unmodified).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Write `observability/grafana/dashboards/business-metrics.json`**

```json
{
  "title": "Business Metrics",
  "uid": "business-metrics",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "graphTooltip": 1,
  "style": "dark",
  "timezone": "browser",
  "tags": ["microservices", "business"],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "10s",
  "templating": {
    "list": [
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(up, job)",
        "includeAll": true,
        "multi": true,
        "current": { "text": "All", "value": "$__all" },
        "refresh": 2,
        "sort": 1
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "Active Users (Successful Logins/sec)",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "rate(auth_requests_total{endpoint=\"/login\",status=\"200\",job=~\"$service\"}[5m])",
          "legendFormat": "successful logins/sec"
        }
      ]
    },
    {
      "id": 2,
      "title": "Login Success Rate",
      "type": "stat",
      "datasource": "Prometheus",
      "gridPos": { "x": 12, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "red", "value": null },
              { "color": "green", "value": 80 }
            ]
          }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] } },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum(rate(auth_requests_total{endpoint=\"/login\",status=\"200\",job=~\"$service\"}[5m])) / sum(rate(auth_requests_total{endpoint=\"/login\",job=~\"$service\"}[5m])) * 100",
          "legendFormat": "login success %"
        }
      ]
    },
    {
      "id": 3,
      "title": "Data Items Served",
      "type": "stat",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] } },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum(rate(data_requests_total{endpoint=\"/data\",status=\"200\"}[5m])) * 3",
          "legendFormat": "items served/sec"
        }
      ]
    },
    {
      "id": 4,
      "title": "API Usage by Endpoint",
      "type": "piechart",
      "datasource": "Prometheus",
      "gridPos": { "x": 8, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum by (endpoint) (increase(gateway_requests_total[$__range]))",
          "legendFormat": "{{endpoint}}"
        }
      ]
    },
    {
      "id": 5,
      "title": "Throttled Requests",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 16, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "rate(gateway_throttled_total[5m])",
          "legendFormat": "throttled/sec"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax and structure**

Run:
```bash
python3 -c "
import json
d = json.load(open('observability/grafana/dashboards/business-metrics.json'))
assert d['title'] == 'Business Metrics'
assert len(d['panels']) == 5
assert any(v['name'] == 'service' for v in d['templating']['list'])
print('OK: 5 panels, service variable present')
"
```
Expected: `OK: 5 panels, service variable present`

- [ ] **Step 3: Commit**

```bash
git add observability/grafana/dashboards/business-metrics.json
git commit -m "feat: add Grafana Business Metrics dashboard"
```

---

### Task 3: Security dashboard

**Files:**
- Create: `observability/grafana/dashboards/security.json`

**Interfaces:**
- Consumes: `auth_requests_total{endpoint,status,job}`, `auth_errors_total{error_type,job}`, `gateway_throttled_total` (Phase 1, live data); `security_vulnerabilities_total{severity}`, `security_score` (forward-declared, populated by Phase 5 — not yet emitted by anything).
- Produces: the metric-naming contract (`security_vulnerabilities_total{severity}`, `security_score`) that Phase 5 must satisfy.

- [ ] **Step 1: Write `observability/grafana/dashboards/security.json`**

```json
{
  "title": "Security",
  "uid": "security-dashboard",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "graphTooltip": 1,
  "style": "dark",
  "timezone": "browser",
  "tags": ["microservices", "security"],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "10s",
  "templating": {
    "list": [
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(up, job)",
        "includeAll": true,
        "multi": true,
        "current": { "text": "All", "value": "$__all" },
        "refresh": 2,
        "sort": 1
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "Failed Auth Attempts",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum(rate(auth_requests_total{endpoint=~\"/login|/validate\",status=\"401\",job=~\"$service\"}[5m]))",
          "legendFormat": "failed auth/sec"
        }
      ]
    },
    {
      "id": 2,
      "title": "Auth Error Breakdown",
      "type": "barchart",
      "datasource": "Prometheus",
      "gridPos": { "x": 12, "y": 0, "w": 12, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum by (error_type) (increase(auth_errors_total{job=~\"$service\"}[$__range]))",
          "legendFormat": "{{error_type}}"
        }
      ]
    },
    {
      "id": 3,
      "title": "Rate Limit Triggers",
      "type": "timeseries",
      "datasource": "Prometheus",
      "gridPos": { "x": 0, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "rate(gateway_throttled_total{job=~\"$service\"}[5m])",
          "legendFormat": "throttled/sec"
        }
      ]
    },
    {
      "id": 4,
      "title": "CVEs Detected",
      "type": "table",
      "datasource": "Prometheus",
      "gridPos": { "x": 8, "y": 8, "w": 8, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "description": "No data until Phase 5's security pipeline populates security_vulnerabilities_total{severity}.",
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "sum by (severity) (security_vulnerabilities_total)",
          "format": "table",
          "instant": true
        }
      ]
    },
    {
      "id": 5,
      "title": "Security Score",
      "type": "gauge",
      "datasource": "Prometheus",
      "gridPos": { "x": 16, "y": 8, "w": 8, "h": 8 },
      "description": "No data until Phase 5's security pipeline populates security_score.",
      "fieldConfig": {
        "defaults": {
          "unit": "none",
          "min": 0,
          "max": 100,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "red", "value": null },
              { "color": "yellow", "value": 50 },
              { "color": "green", "value": 80 }
            ]
          }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"] } },
      "targets": [
        {
          "refId": "A",
          "datasource": "Prometheus",
          "expr": "security_score"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax and structure**

Run:
```bash
python3 -c "
import json
d = json.load(open('observability/grafana/dashboards/security.json'))
assert d['title'] == 'Security'
assert len(d['panels']) == 5
assert any(v['name'] == 'service' for v in d['templating']['list'])
print('OK: 5 panels, service variable present')
"
```
Expected: `OK: 5 panels, service variable present`

- [ ] **Step 3: Commit**

```bash
git add observability/grafana/dashboards/security.json
git commit -m "feat: add Grafana Security dashboard"
```

---

### Task 4: Logs dashboard

**Files:**
- Create: `observability/grafana/dashboards/logs.json`

**Interfaces:**
- Consumes: Loki log streams labeled `container` (Phase 2's Promtail config, values `api-gateway`/`auth-service`/`data-service`), each line a JSON object with a `level` field (Phase 1's structured logging).
- Produces: nothing consumed by other tasks.

- [ ] **Step 1: Write `observability/grafana/dashboards/logs.json`**

```json
{
  "title": "Logs",
  "uid": "logs-dashboard",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "graphTooltip": 1,
  "style": "dark",
  "timezone": "browser",
  "tags": ["microservices", "logs"],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "10s",
  "templating": {
    "list": [
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": "Prometheus",
        "query": "label_values(up, job)",
        "includeAll": true,
        "multi": true,
        "current": { "text": "All", "value": "$__all" },
        "refresh": 2,
        "sort": 1
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "Log Volume by Service",
      "type": "timeseries",
      "datasource": "Loki",
      "gridPos": { "x": 0, "y": 0, "w": 24, "h": 8 },
      "fieldConfig": { "defaults": { "unit": "short" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": "Loki",
          "expr": "sum by (container) (count_over_time({container=~\"$service\"}[$__interval]))",
          "legendFormat": "{{container}}"
        }
      ]
    },
    {
      "id": 2,
      "title": "Errors & Warnings",
      "type": "logs",
      "datasource": "Loki",
      "gridPos": { "x": 0, "y": 8, "w": 12, "h": 10 },
      "options": { "showTime": true, "sortOrder": "Descending", "enableLogDetails": true },
      "targets": [
        {
          "refId": "A",
          "datasource": "Loki",
          "expr": "{container=~\"$service\"} | json | level=~\"ERROR|WARNING\""
        }
      ]
    },
    {
      "id": 3,
      "title": "Live Tail",
      "type": "logs",
      "datasource": "Loki",
      "gridPos": { "x": 12, "y": 8, "w": 12, "h": 10 },
      "options": { "showTime": true, "sortOrder": "Descending", "enableLogDetails": true },
      "targets": [
        {
          "refId": "A",
          "datasource": "Loki",
          "expr": "{container=~\"$service\"}"
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Validate JSON syntax and structure**

Run:
```bash
python3 -c "
import json
d = json.load(open('observability/grafana/dashboards/logs.json'))
assert d['title'] == 'Logs'
assert len(d['panels']) == 3
assert any(v['name'] == 'service' for v in d['templating']['list'])
print('OK: 3 panels, service variable present')
"
```
Expected: `OK: 3 panels, service variable present`

- [ ] **Step 3: Commit**

```bash
git add observability/grafana/dashboards/logs.json
git commit -m "feat: add Grafana Logs dashboard"
```

---

### Task 5: Bring up the stack and verify all 4 dashboards end-to-end

**Files:** none (verification only)

- [ ] **Step 1: Bring up the full stack**

Run: `docker compose up -d`
Expected: all 9 containers created/started (Grafana picks up the 4 new JSON files from its already-mounted `observability/grafana/dashboards/` bind mount with no config change needed).

- [ ] **Step 2: Wait for healthchecks**

Run:
```bash
sleep 20
docker compose ps
```
Expected: `prometheus`, `loki`, `grafana`, `auth-service`, `data-service`, `api-gateway` show `(healthy)`; `alertmanager`, `promtail`, `jaeger` show `Up`.

- [ ] **Step 3: Confirm Grafana loaded all 4 dashboards**

Run:
```bash
curl -s -u admin:admin 'http://localhost:3000/api/search?type=dash-db' | python3 -c "
import json, sys
titles = sorted(d['title'] for d in json.load(sys.stdin))
print(titles)
"
```
Expected: `['Business Metrics', 'Logs', 'Security', 'Service Overview']`

- [ ] **Step 4: Generate traffic so metrics-backed panels have data**

Run:
```bash
TOKEN=$(curl -s -X POST localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
for i in $(seq 1 10); do curl -s localhost:5000/api/data -H "Authorization: Bearer $TOKEN" > /dev/null; sleep 1; done
echo "done"
```
Expected: `done`.

- [ ] **Step 5: Confirm the `$service` variable's underlying query resolves to the 3 services**

Run:
```bash
sleep 15
curl -s 'http://localhost:9090/api/v1/label/job/values' | python3 -m json.tool
```
Expected: `"data"` is `["api-gateway", "auth-service", "data-service", "prometheus"]` (Prometheus's own `job` is expected too; the dashboard variable still resolves the 3 microservice names correctly since the panels filter on them by exact value, not exclude `prometheus`).

- [ ] **Step 6: Confirm the Service Overview dashboard's panel data matches Prometheus directly**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/query?query=service:request_rate:rate5m' | python3 -m json.tool
```
Expected: `"status": "success"` with one result entry per service (`api-gateway`, `auth-service`, `data-service`), non-negative values — this is exactly what Service Overview's "Request Rate" panel renders.

- [ ] **Step 7: Stop one service and confirm its status flips, matching the Service Status panel's data source**

Run:
```bash
docker compose stop data-service
sleep 20
curl -s 'http://localhost:9090/api/v1/query?query=up{job="data-service"}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['data']['result'][0]['value'][1])
"
```
Expected: `0` (the Service Status panel's value mapping renders this as a red "DOWN" tile).

- [ ] **Step 8: Restart the service**

Run:
```bash
docker compose start data-service
sleep 15
curl -s 'http://localhost:9090/api/v1/query?query=up{job="data-service"}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['data']['result'][0]['value'][1])
"
```
Expected: `1`.

- [ ] **Step 9: Confirm Loki has log data for the Logs dashboard's panels, including the level-filtered query**

Run:
```bash
curl -s -G 'http://localhost:3100/loki/api/v1/query' --data-urlencode 'query={container=~"api-gateway|auth-service|data-service"}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data['data']['result']), 'streams')
"
curl -s -G 'http://localhost:3100/loki/api/v1/query' --data-urlencode 'query={container=~"api-gateway|auth-service|data-service"} | json | level=~"ERROR|WARNING"' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['status'])
"
```
Expected: first command prints a number greater than 0 (`N streams`), confirming "Log Volume by Service" and "Live Tail" have real data; second prints `success`, confirming "Errors & Warnings" panel's exact LogQL (`| json | level=~"ERROR|WARNING"`) parses and runs without error (the Rate Limiter's `logger.warning("Rate limit exceeded...")` from Phase 1 is one real source of a `WARNING`-level line if traffic exceeded 20 req/10s; an empty result set is still acceptable here since the goal is confirming the query executes, not that a warning necessarily fired).

- [ ] **Step 10: Confirm the Security dashboard's live panels have data and the forward-declared ones correctly show none yet**

Run:
```bash
curl -s 'http://localhost:9090/api/v1/query?query=rate(gateway_throttled_total[5m])' | python3 -c "
import json, sys
print(json.load(sys.stdin)['status'])
"
curl -s 'http://localhost:9090/api/v1/query?query=security_score' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data['status'], len(data['data']['result']))
"
```
Expected: first command prints `success`; second prints `success 0` (zero results — confirms "No data" is the expected, not-broken, state for the Phase-5-dependent panel).

- [ ] **Step 11: Regression check — re-run the Phase 1 test suite**

Run: `cd microservices && .venv/bin/pytest tests/ -v`
Expected: all tests pass (this phase touched no application code, so this is a sanity check, not expected to surface anything new).

- [ ] **Step 12: Tear down**

Run: `docker compose down`
Expected: all 9 containers stopped and removed; named volumes intact (no `-v` flag used).

- [ ] **Step 13: Confirm nothing is left uncommitted**

Run: `git status`
Expected: working tree clean (this task is verification-only; everything was already committed in Tasks 1–4).
