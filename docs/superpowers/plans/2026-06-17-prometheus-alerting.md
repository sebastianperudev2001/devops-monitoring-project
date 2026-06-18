# Prometheus Rules & Alerting (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Prometheus recording rules + alert rules covering all 3 microservices, and wire Alertmanager to route every alert to Slack, per `docs/superpowers/specs/2026-06-17-prometheus-alerting-design.md`.

**Architecture:** Two new YAML files dropped into the already-mounted `observability/prometheus/rules/` directory (no `prometheus.yml` edit needed — Phase 2 already globs `*.yml` there). 3 recording rules × 3 services = 9 entries sharing one `service` label; 6 alerts read those recording rules (plus `label_replace` on raw `up`/process metrics) so each alert type is written once, not once per service. Alertmanager's stub config is replaced with a real route + Slack receiver using `api_url_file`, reading from a new tracked placeholder file mounted into the container — the only `docker-compose.yml` change this phase needs.

**Tech Stack:** Prometheus rule files (PromQL), Alertmanager config (`slack_configs`), validated with `promtool`/`amtool` via the same pinned images from Phase 2 (`prom/prometheus:v2.54.1`, `prom/alertmanager:v0.27.0`) before touching the live stack.

---

## File Structure

```
observability/
├── prometheus/
│   └── rules/
│       ├── recording-rules.yml   # NEW
│       └── alert-rules.yml       # NEW
└── alertmanager/
    ├── alertmanager.yml          # MODIFIED
    └── secrets/
        └── slack_webhook_url     # NEW (tracked placeholder)
docker-compose.yml                 # MODIFIED (one new volume line on alertmanager service)
```

---

### Task 1: Recording rules

**Files:**
- Create: `observability/prometheus/rules/recording-rules.yml`

- [ ] **Step 1: Write `observability/prometheus/rules/recording-rules.yml`**

```yaml
groups:
  - name: service_golden_signals
    rules:
      - record: service:request_rate:rate5m
        expr: sum(rate(gateway_requests_total[5m]))
        labels:
          service: api-gateway
      - record: service:request_rate:rate5m
        expr: sum(rate(auth_requests_total[5m]))
        labels:
          service: auth-service
      - record: service:request_rate:rate5m
        expr: sum(rate(data_requests_total[5m]))
        labels:
          service: data-service

      - record: service:error_ratio:rate5m
        expr: sum(rate(gateway_requests_total{status=~"5.."}[5m])) / sum(rate(gateway_requests_total[5m]))
        labels:
          service: api-gateway
      - record: service:error_ratio:rate5m
        expr: sum(rate(auth_requests_total{status=~"5.."}[5m])) / sum(rate(auth_requests_total[5m]))
        labels:
          service: auth-service
      - record: service:error_ratio:rate5m
        expr: sum(rate(data_requests_total{status=~"5.."}[5m])) / sum(rate(data_requests_total[5m]))
        labels:
          service: data-service

      - record: service:request_latency_p95:5m
        expr: histogram_quantile(0.95, sum(rate(gateway_request_duration_seconds_bucket[5m])) by (le))
        labels:
          service: api-gateway
      - record: service:request_latency_p95:5m
        expr: histogram_quantile(0.95, sum(rate(auth_request_duration_seconds_bucket[5m])) by (le))
        labels:
          service: auth-service
      - record: service:request_latency_p95:5m
        expr: histogram_quantile(0.95, sum(rate(data_request_duration_seconds_bucket[5m])) by (le))
        labels:
          service: data-service
```

- [ ] **Step 2: Validate with promtool**

Run:
```bash
docker run --rm --entrypoint=promtool -v "$(pwd)/observability/prometheus/rules:/etc/prometheus/rules" prom/prometheus:v2.54.1 check rules /etc/prometheus/rules/recording-rules.yml
```
Expected: exit code 0, output includes `SUCCESS: 9 rules found` (exact wording can vary slightly by promtool version — the pass signal is exit 0 and no `FAILED`/error text).

- [ ] **Step 3: Commit**

```bash
git add observability/prometheus/rules/recording-rules.yml
git commit -m "feat: add Prometheus recording rules for the 3 services' golden signals"
```

---

### Task 2: Alert rules

**Files:**
- Create: `observability/prometheus/rules/alert-rules.yml`

- [ ] **Step 1: Write `observability/prometheus/rules/alert-rules.yml`**

```yaml
groups:
  - name: microservices_alerts
    rules:
      - alert: HighErrorRate
        expr: service:error_ratio:rate5m > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on {{ $labels.service }}"
          description: "{{ $labels.service }} 5xx error ratio is {{ $value | humanizePercentage }} over the last 5m (threshold 1%)."

      - alert: HighLatency
        expr: service:request_latency_p95:5m > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High p95 latency on {{ $labels.service }}"
          description: "{{ $labels.service }} p95 request latency is {{ $value | humanizeDuration }} over the last 5m (threshold 500ms)."

      - alert: ServiceDown
        expr: label_replace(up{job=~"api-gateway|auth-service|data-service"}, "service", "$1", "job", "(.+)") == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.service }} is down"
          description: "{{ $labels.service }} has been unreachable by Prometheus for more than 1 minute."

      - alert: LowThroughput
        expr: service:request_rate:rate5m < 0.1667
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low throughput on {{ $labels.service }}"
          description: "{{ $labels.service }} is handling {{ $value | humanize }} req/s (below the 10 req/min threshold) over the last 5m."

      - alert: HighCPUUsage
        expr: label_replace(rate(process_cpu_seconds_total{job=~"api-gateway|auth-service|data-service"}[5m]), "service", "$1", "job", "(.+)") > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.service }}"
          description: "{{ $labels.service }} CPU usage is {{ $value | humanizePercentage }} of one core, averaged over the last 5m (threshold 80%)."

      - alert: HighMemoryUsage
        expr: label_replace(process_resident_memory_bytes{job=~"api-gateway|auth-service|data-service"}, "service", "$1", "job", "(.+)") > 3e8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.service }}"
          description: "{{ $labels.service }} resident memory is {{ $value | humanize1024 }}B (threshold 300MB)."
```

- [ ] **Step 2: Validate with promtool**

Run:
```bash
docker run --rm --entrypoint=promtool -v "$(pwd)/observability/prometheus/rules:/etc/prometheus/rules" prom/prometheus:v2.54.1 check rules /etc/prometheus/rules/alert-rules.yml
```
Expected: exit code 0, output includes `SUCCESS: 6 rules found`.

- [ ] **Step 3: Commit**

```bash
git add observability/prometheus/rules/alert-rules.yml
git commit -m "feat: add 6 Prometheus alerts covering error rate, latency, downtime, throughput, CPU and memory"
```

---

### Task 3: Alertmanager Slack receiver

**Files:**
- Create: `observability/alertmanager/secrets/slack_webhook_url`
- Modify: `observability/alertmanager/alertmanager.yml`
- Modify: `docker-compose.yml:40` (add one volume line to the `alertmanager` service)

- [ ] **Step 1: Create the tracked placeholder secret file**

```bash
mkdir -p observability/alertmanager/secrets
printf '%s' 'https://hooks.slack.com/services/REPLACE/ME/PLACEHOLDER' > observability/alertmanager/secrets/slack_webhook_url
```

- [ ] **Step 2: Replace `observability/alertmanager/alertmanager.yml`'s contents**

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
        text: '{{ range .Alerts }}{{ .Annotations.description }}\n{{ end }}'
```

- [ ] **Step 3: Validate with amtool, mounting the secrets file at the same path the container will use**

Run:
```bash
docker run --rm --entrypoint=amtool \
  -v "$(pwd)/observability/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml" \
  -v "$(pwd)/observability/alertmanager/secrets:/etc/alertmanager/secrets" \
  prom/alertmanager:v0.27.0 check-config /etc/alertmanager/alertmanager.yml
```
Expected:
```
Checking '/etc/alertmanager/alertmanager.yml'  SUCCESS
Found:
 - global config
 - route
 - 0 inhibit rules
 - 1 receivers
 - 0 templates
```

- [ ] **Step 4: Add the secrets volume mount to the `alertmanager` service in `docker-compose.yml`**

Change (lines 39-41):
```yaml
    volumes:
      - ./observability/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager
```
to:
```yaml
    volumes:
      - ./observability/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - ./observability/alertmanager/secrets/slack_webhook_url:/etc/alertmanager/secrets/slack_webhook_url:ro
      - alertmanager_data:/alertmanager
```

- [ ] **Step 5: Validate Compose syntax**

Run: `docker compose config`
Expected: resolved config prints with no error, exit code 0, and shows the new bind mount under the `alertmanager` service's volumes.

- [ ] **Step 6: Commit**

```bash
git add observability/alertmanager docker-compose.yml
git commit -m "feat: route Prometheus alerts to Slack via Alertmanager"
```

---

### Task 4: Bring up the stack and verify end-to-end

**Files:** none (verification only)

- [ ] **Step 1: Bring up the full stack**

Run: `docker compose up -d`
Expected: the `alertmanager` container recreated (its config changed since Phase 2); the other 8 created and started (the stack was fully down before this task — confirmed via `docker compose ps` returning no rows). No `--build` needed: the 3 microservice images already exist from Phase 2/this session and their Dockerfiles are unchanged.

- [ ] **Step 2: Wait for healthchecks, confirm all 9 containers are up**

Run:
```bash
sleep 20
docker compose ps
```
Expected: `prometheus`, `loki`, `grafana`, `auth-service`, `data-service`, `api-gateway` show `(healthy)`; `alertmanager`, `promtail`, `jaeger` show `Up`.

- [ ] **Step 3: Confirm both new rule groups loaded with no errors**

Run:
```bash
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import json, sys
data = json.load(sys.stdin)
for group in data['data']['groups']:
    print(group['name'], '-', len(group['rules']), 'rules')
"
```
Expected:
```
service_golden_signals - 9 rules
microservices_alerts - 6 rules
```
(Group order may vary.) If any rule shows a non-empty `"lastError"` field, stop and fix the expression before continuing.

- [ ] **Step 4: Generate a little traffic so the recording rules have data to compute over**

Run:
```bash
TOKEN=$(curl -s -X POST localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
for i in $(seq 1 10); do curl -s localhost:5000/api/data -H "Authorization: Bearer $TOKEN" > /dev/null; sleep 1; done
echo "done"
```
Expected: `done`.

- [ ] **Step 5: Confirm the recording rules are producing series**

Run:
```bash
sleep 20
curl -s 'http://localhost:9090/api/v1/query?query=service:request_rate:rate5m' | python3 -m json.tool
```
Expected: `"status": "success"` with a non-empty `"result"` array containing one entry per service (`"service":"api-gateway"`, `"auth-service"`, `"data-service"`), each with a non-negative numeric value.

- [ ] **Step 6: Force `ServiceDown` and confirm it fires**

Run:
```bash
docker compose stop auth-service
sleep 95
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import json, sys
data = json.load(sys.stdin)
for a in data['data']['alerts']:
    if a['labels']['alertname'] == 'ServiceDown':
        print(a['labels']['service'], a['state'])
"
```
Expected: `auth-service firing`. The 95s sleep covers the worst case: up to 15s until the next scrape marks `up=0`, the full 60s `for: 1m` duration, and up to 15s until the next rule evaluation notices.

- [ ] **Step 7: Confirm the firing alert reached Alertmanager and a Slack notify attempt was made**

Run:
```bash
curl -s http://localhost:9093/api/v2/alerts | python3 -c "
import json, sys
data = json.load(sys.stdin)
for a in data:
    print(a['labels'].get('alertname'), a['labels'].get('service'), a['status']['state'])
"
docker compose logs alertmanager | grep -i slack
```
Expected: the first command lists `ServiceDown auth-service active`; the second shows at least one log line mentioning a Slack notify attempt (it will report a delivery failure or an HTTP response from `hooks.slack.com` since the URL is a placeholder — that's expected and confirms the routing/receiver wiring is correct independent of real delivery, per the spec's accepted limitation).

- [ ] **Step 8: Restart the stopped service and confirm the alert resolves**

Run:
```bash
docker compose start auth-service
sleep 20
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import json, sys
data = json.load(sys.stdin)
names = [a['labels']['alertname'] for a in data['data']['alerts'] if a['labels'].get('service') == 'auth-service']
print(names)
"
```
Expected: `[]` (empty list) or a list no longer containing `ServiceDown` — confirming the alert cleared once the service came back.

- [ ] **Step 9: Regression check — re-run the Phase 1 test suite**

Run: `cd microservices && .venv/bin/pytest tests/ -v`
Expected: `25 passed` (this phase touched no application code, so this is a sanity check, not expected to surface anything new).

- [ ] **Step 10: Tear down**

Run: `docker compose down`
Expected: all 9 containers stopped and removed; named volumes intact (no `-v` flag used).

- [ ] **Step 11: Confirm nothing is left uncommitted**

Run: `git status`
Expected: working tree clean (this task is verification-only; everything was already committed in Tasks 1–3).
