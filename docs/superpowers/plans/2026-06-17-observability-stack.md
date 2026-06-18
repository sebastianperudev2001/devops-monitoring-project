# Observability Stack (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a Docker Compose stack that runs the 3 Phase 1 microservices alongside Prometheus, Grafana, Loki+Promtail, Jaeger, and Alertmanager, fully wired so metrics/logs/traces actually flow end-to-end, per `docs/superpowers/specs/2026-06-17-observability-stack-design.md`.

**Architecture:** One `docker-compose.yml` at the repo root (explicit `name: devops-monitoring` so the Compose project name is deterministic regardless of checkout directory), 9 containers on one bridge network (`observability-net`). Config-as-code under `observability/{prometheus,alertmanager,loki,promtail,grafana}/`. Named volumes for all 5 stateful components (Prometheus, Grafana, Loki, Alertmanager, Jaeger via Badger) so data survives restarts. Promtail discovers the other containers via the Docker socket, filtered to this Compose project only.

**Tech Stack:** Docker Compose, `prom/prometheus:v2.54.1`, `prom/alertmanager:v0.27.0`, `grafana/loki:3.1.1`, `grafana/promtail:3.1.1`, `grafana/grafana:11.2.0`, `jaegertracing/all-in-one:1.60` — all 6 tags confirmed pullable during planning.

---

## File Structure

```
docker-compose.yml
observability/
├── prometheus/
│   ├── prometheus.yml
│   └── rules/.gitkeep
├── alertmanager/
│   └── alertmanager.yml
├── loki/
│   └── loki-config.yml
├── promtail/
│   └── promtail-config.yml
└── grafana/
    ├── provisioning/
    │   ├── datasources/datasources.yml
    │   └── dashboards/dashboards.yml
    └── dashboards/.gitkeep
```

---

### Task 1: Prometheus scrape config

**Files:**
- Create: `observability/prometheus/prometheus.yml`
- Create: `observability/prometheus/rules/.gitkeep`

- [ ] **Step 1: Create the rules placeholder directory**

```bash
mkdir -p observability/prometheus/rules
touch observability/prometheus/rules/.gitkeep
```

- [ ] **Step 2: Write `observability/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ['localhost:9090']

  - job_name: api-gateway
    static_configs:
      - targets: ['api-gateway:5000']

  - job_name: auth-service
    static_configs:
      - targets: ['auth-service:5001']

  - job_name: data-service
    static_configs:
      - targets: ['data-service:5002']
```

- [ ] **Step 3: Validate with promtool**

Run:
```bash
docker run --rm --entrypoint=promtool -v "$(pwd)/observability/prometheus:/etc/prometheus" prom/prometheus:v2.54.1 check config /etc/prometheus/prometheus.yml
```
Expected:
```
Checking /etc/prometheus/prometheus.yml
 SUCCESS: /etc/prometheus/prometheus.yml is valid prometheus config file syntax
```

- [ ] **Step 4: Commit**

```bash
git add observability/prometheus
git commit -m "feat: add Prometheus scrape config for the 3 microservices"
```

---

### Task 2: Alertmanager stub config

**Files:**
- Create: `observability/alertmanager/alertmanager.yml`

- [ ] **Step 1: Write `observability/alertmanager/alertmanager.yml`**

```yaml
route:
  receiver: default

receivers:
  - name: default
```

This is intentionally a no-op: one receiver with no integrations, so Prometheus has a live Alertmanager to talk to. Phase 3 replaces this file's contents with real routing + a Slack receiver; nothing else in the stack needs to change when that happens.

- [ ] **Step 2: Validate with amtool**

Run:
```bash
docker run --rm --entrypoint=amtool -v "$(pwd)/observability/alertmanager:/etc/alertmanager" prom/alertmanager:v0.27.0 check-config /etc/alertmanager/alertmanager.yml
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

- [ ] **Step 3: Commit**

```bash
git add observability/alertmanager
git commit -m "feat: add Alertmanager stub config"
```

---

### Task 3: Loki config

**Files:**
- Create: `observability/loki/loki-config.yml`

- [ ] **Step 1: Write `observability/loki/loki-config.yml`**

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
```

- [ ] **Step 2: Validate with Loki's own config verifier**

Run:
```bash
docker run --rm -v "$(pwd)/observability/loki:/etc/loki" grafana/loki:3.1.1 -config.file=/etc/loki/loki-config.yml -verify-config
```
Expected: a line containing `msg="config is valid"`, then the process exits (no need to interrupt it).

- [ ] **Step 3: Commit**

```bash
git add observability/loki
git commit -m "feat: add Loki single-binary filesystem-storage config"
```

---

### Task 4: Promtail config

**Files:**
- Create: `observability/promtail/promtail-config.yml`

- [ ] **Step 1: Write `observability/promtail/promtail-config.yml`**

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker-containers
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
        filters:
          - name: label
            values: ["com.docker.compose.project=devops-monitoring"]
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: container
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: logstream
```

The `filters` block scopes discovery to containers from this Compose project only (matching the `name: devops-monitoring` set in `docker-compose.yml` in Task 6) — without it, Promtail would discover and tail logs from every container running anywhere on the host's Docker engine, not just this stack's.

- [ ] **Step 2: Sanity-check the config loads (no live Docker socket yet — connection error here is expected)**

Run:
```bash
docker run -d --name promtail-config-check -v "$(pwd)/observability/promtail/promtail-config.yml:/etc/promtail/promtail-config.yml" grafana/promtail:3.1.1 -config.file=/etc/promtail/promtail-config.yml -dry-run
sleep 3
docker logs promtail-config-check
docker rm -f promtail-config-check
```
Expected: log lines including `msg="Starting Promtail"` and `msg="server listening on addresses"`. You'll also see a `level=error ... msg="Unable to refresh target groups" err="error while listing containers: Cannot connect to the Docker daemon..."` line — that's expected here since the Docker socket isn't mounted in this isolated check; it confirms the YAML/schema parsed correctly and the server started despite no targets being discoverable yet. This file's real validation (discovery actually working) happens in Task 6, once the socket is mounted and real containers exist to discover.

- [ ] **Step 3: Commit**

```bash
git add observability/promtail
git commit -m "feat: add Promtail config to ship container logs to Loki"
```

---

### Task 5: Grafana provisioning (datasources + dashboard placeholder)

**Files:**
- Create: `observability/grafana/provisioning/datasources/datasources.yml`
- Create: `observability/grafana/provisioning/dashboards/dashboards.yml`
- Create: `observability/grafana/dashboards/.gitkeep`

- [ ] **Step 1: Write `observability/grafana/provisioning/datasources/datasources.yml`**

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100

  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
```

- [ ] **Step 2: Write `observability/grafana/provisioning/dashboards/dashboards.yml`**

```yaml
apiVersion: 1

providers:
  - name: default
    type: file
    folder: ''
    options:
      path: /etc/grafana/dashboards
```

- [ ] **Step 3: Create the empty dashboards placeholder directory**

```bash
mkdir -p observability/grafana/dashboards
touch observability/grafana/dashboards/.gitkeep
```

- [ ] **Step 4: Validate by running Grafana standalone and querying its datasources API**

Run:
```bash
docker run -d --name grafana-config-check \
  -v "$(pwd)/observability/grafana/provisioning:/etc/grafana/provisioning" \
  -v "$(pwd)/observability/grafana/dashboards:/etc/grafana/dashboards" \
  -e GF_SECURITY_ADMIN_USER=admin -e GF_SECURITY_ADMIN_PASSWORD=admin \
  -p 13000:3000 \
  grafana/grafana:11.2.0
sleep 8
curl -s -u admin:admin http://localhost:13000/api/datasources
docker rm -f grafana-config-check
```
Expected: a JSON array with exactly 3 objects, `"name"` values `"Jaeger"`, `"Loki"`, `"Prometheus"` (order may vary), and `"Prometheus"` showing `"isDefault":true`.

- [ ] **Step 5: Commit**

```bash
git add observability/grafana
git commit -m "feat: provision Grafana with Prometheus/Loki/Jaeger datasources"
```

---

### Task 6: docker-compose.yml — observability stack only

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
name: devops-monitoring

networks:
  observability-net:
    driver: bridge

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
  alertmanager_data:
  jaeger_data:

services:
  prometheus:
    image: prom/prometheus:v2.54.1
    container_name: prometheus
    networks: [observability-net]
    ports:
      - "9090:9090"
    volumes:
      - ./observability/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./observability/prometheus/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    depends_on:
      - alertmanager
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/healthy"]
      interval: 10s
      timeout: 5s
      retries: 5

  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: alertmanager
    networks: [observability-net]
    ports:
      - "9093:9093"
    volumes:
      - ./observability/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager

  loki:
    image: grafana/loki:3.1.1
    container_name: loki
    networks: [observability-net]
    ports:
      - "3100:3100"
    volumes:
      - ./observability/loki/loki-config.yml:/etc/loki/loki-config.yml:ro
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yml
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3100/ready"]
      interval: 10s
      timeout: 5s
      retries: 5

  promtail:
    image: grafana/promtail:3.1.1
    container_name: promtail
    networks: [observability-net]
    volumes:
      - ./observability/promtail/promtail-config.yml:/etc/promtail/promtail-config.yml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    command: -config.file=/etc/promtail/promtail-config.yml
    depends_on:
      - loki

  jaeger:
    image: jaegertracing/all-in-one:1.60
    container_name: jaeger
    user: root
    networks: [observability-net]
    ports:
      - "16686:16686"
      - "4317:4317"
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
      SPAN_STORAGE_TYPE: badger
      BADGER_EPHEMERAL: "false"
      BADGER_DIRECTORY_VALUE: /badger/data
      BADGER_DIRECTORY_KEY: /badger/key
    volumes:
      - jaeger_data:/badger

  grafana:
    image: grafana/grafana:11.2.0
    container_name: grafana
    networks: [observability-net]
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./observability/grafana/dashboards:/etc/grafana/dashboards:ro
      - grafana_data:/var/lib/grafana
    depends_on:
      prometheus:
        condition: service_healthy
      loki:
        condition: service_healthy
      jaeger:
        condition: service_started
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

The Jaeger service's `user: root` override exists because `jaegertracing/all-in-one:1.60` runs as non-root UID 10001 by default, but Docker creates the named `jaeger_data` volume owned by `root:root` — without the override, Jaeger fails at startup with `mkdir /badger/key: permission denied` since UID 10001 can't write into that volume. Running this one container as root sidesteps the ownership mismatch; nothing else in the stack needs this treatment.

- [ ] **Step 2: Validate Compose syntax**

Run: `docker compose config`
Expected: the fully-resolved config prints to stdout with no error, exit code 0.

- [ ] **Step 3: Bring up the observability stack**

Run: `docker compose up -d`
Expected: 6 containers created and started (`prometheus`, `alertmanager`, `loki`, `promtail`, `jaeger`, `grafana`).

- [ ] **Step 4: Wait for healthchecks, then confirm container states**

Run:
```bash
sleep 20
docker compose ps
```
Expected: `prometheus`, `loki`, `grafana` show `(healthy)`; `alertmanager`, `promtail`, `jaeger` show `Up` (no healthcheck defined for these three — see spec's rationale).

- [ ] **Step 5: Confirm each component's health endpoint**

Run:
```bash
curl -s http://localhost:9090/-/healthy
curl -s http://localhost:9093/-/healthy
curl -s http://localhost:3100/ready
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:16686/
curl -s http://localhost:3000/api/health
docker compose exec promtail wget -qO- http://localhost:9080/ready
```
Expected, in order: `Prometheus Server is Healthy.`, `OK`, `ready`, `200`, JSON containing `"database":"ok"`, `Ready`.

- [ ] **Step 6: Confirm Promtail's Docker discovery is working with no errors**

Run: `docker compose logs promtail | grep -i error`
Expected: no output (the Docker-daemon-connection error from Task 4's isolated check should not appear now that the socket is mounted for real).

- [ ] **Step 7: Confirm Grafana's datasources are live**

Run: `curl -s -u admin:admin http://localhost:3000/api/datasources`
Expected: JSON array with 3 datasources (Prometheus, Loki, Jaeger), same as Task 5's check.

- [ ] **Step 8: Tear down**

Run: `docker compose down`
Expected: all 6 containers stopped and removed; named volumes remain (no `-v` flag used).

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Docker Compose stack for Prometheus/Grafana/Loki/Promtail/Jaeger/Alertmanager"
```

---

### Task 7: Wire the 3 microservices into the Compose stack

**Files:**
- Modify: `docker-compose.yml` (append 3 new service blocks under `services:`, after the `grafana:` block)

- [ ] **Step 1: Append the 3 microservice blocks to `docker-compose.yml`**

```yaml
  auth-service:
    build:
      context: ./microservices
      dockerfile: Dockerfile.auth-service
    container_name: auth-service
    networks: [observability-net]
    ports:
      - "5001:5001"
    environment:
      JAEGER_OTLP_ENDPOINT: jaeger:4317
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"]
      interval: 10s
      timeout: 5s
      retries: 5

  data-service:
    build:
      context: ./microservices
      dockerfile: Dockerfile.data-service
    container_name: data-service
    networks: [observability-net]
    ports:
      - "5002:5002"
    environment:
      JAEGER_OTLP_ENDPOINT: jaeger:4317
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5002/health')"]
      interval: 10s
      timeout: 5s
      retries: 5

  api-gateway:
    build:
      context: ./microservices
      dockerfile: Dockerfile.api-gateway
    container_name: api-gateway
    networks: [observability-net]
    ports:
      - "5000:5000"
    environment:
      AUTH_SERVICE_URL: http://auth-service:5001
      DATA_SERVICE_URL: http://data-service:5002
      JAEGER_OTLP_ENDPOINT: jaeger:4317
    depends_on:
      auth-service:
        condition: service_healthy
      data-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Validate Compose syntax**

Run: `docker compose config`
Expected: resolved config prints with no error, now showing 9 services total.

- [ ] **Step 3: Build and bring up the full stack**

Run: `docker compose up -d --build`
Expected: 3 images built (`devops-monitoring-api-gateway`, `devops-monitoring-auth-service`, `devops-monitoring-data-service`), all 9 containers created and started.

- [ ] **Step 4: Confirm all 9 containers are healthy/running**

Run:
```bash
sleep 20
docker compose ps
```
Expected: `prometheus`, `loki`, `grafana`, `auth-service`, `data-service`, `api-gateway` show `(healthy)`; `alertmanager`, `promtail`, `jaeger` show `Up`.

- [ ] **Step 5: Confirm Prometheus is scraping all 3 services successfully**

Run: `curl -s http://localhost:9090/api/v1/targets | grep -o '"health":"[a-z]*"'`
Expected: 4 lines of `"health":"up"` (Prometheus itself + api-gateway + auth-service + data-service).

- [ ] **Step 6: Generate real traffic through the gateway**

Run:
```bash
TOKEN=$(curl -s -X POST localhost:5001/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
for i in $(seq 1 5); do curl -s localhost:5000/api/data -H "Authorization: Bearer $TOKEN" > /dev/null; done
echo "done"
```
Expected: `done` (each curl returns the aggregated `{"data": [...], "count": 3}` payload silently).

- [ ] **Step 7: Confirm a connected trace shows up in Jaeger**

Run:
```bash
sleep 3
curl -s "http://localhost:16686/api/traces?service=api-gateway&limit=5" | grep -o '"operationName":"[a-zA-Z-]*"' | sort -u
```
Expected: includes at minimum `"operationName":"api-gateway-get-data"`, `"operationName":"call-auth-service"`, `"operationName":"call-data-service"` — confirming one trace spans both downstream calls (the "3+ levels of spans" requirement).

- [ ] **Step 8: Confirm logs are queryable in Loki and share a `request_id` across all 3 services**

Run:
```bash
curl -s localhost:5000/api/data -H "Authorization: Bearer $TOKEN" -D /tmp/gw_headers.txt -o /dev/null
REQUEST_ID=$(grep -i '^x-request-id:' /tmp/gw_headers.txt | tr -d '\r' | cut -d' ' -f2)
echo "request_id: $REQUEST_ID"
sleep 3
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={container=~\"api-gateway|auth-service|data-service\"} |= \"$REQUEST_ID\"" \
  --data-urlencode 'limit=20' | python3 -m json.tool
```
Expected: a non-empty `REQUEST_ID` value, and the Loki response shows `"status": "success"` with a `"result"` array containing log lines from all 3 containers (check the `"container"` label on each stream), each with that same `request_id` value in its JSON message body — confirming one client request produces correlated logs across all 3 services.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: wire the 3 microservices into the Docker Compose observability stack"
```

---

### Task 8: Persistence check and regression test

**Files:** none (verification only)

- [ ] **Step 1: Restart the stack and confirm metrics history survived**

Run:
```bash
docker compose down
docker compose up -d
sleep 20
NOW=$(date +%s)
START=$((NOW - 600))
curl -s "http://localhost:9090/api/v1/query_range?query=up%7Bjob%3D%22api-gateway%22%7D&start=${START}&end=${NOW}&step=15" | python3 -m json.tool
```
Expected: `"status": "success"` with a non-empty `"values"` array containing samples timestamped from before this restart — proving Prometheus's TSDB volume persisted across `docker compose down`/`up`.

- [ ] **Step 2: Confirm Grafana's datasources are still provisioned after restart**

Run: `curl -s -u admin:admin http://localhost:3000/api/datasources`
Expected: same 3 datasources as before (Prometheus, Loki, Jaeger) — provisioning re-applies on every container start regardless of volume state, so this should pass even if it were ephemeral, but confirms nothing broke.

- [ ] **Step 3: Tear down**

Run: `docker compose down`
Expected: all 9 containers stopped and removed, named volumes intact.

- [ ] **Step 4: Re-run the Phase 1 test suite to confirm this phase didn't break anything**

Run: `cd microservices && .venv/bin/pytest tests/ -v`
Expected: `25 passed`. You may see harmless `Transient error ... exporting traces to localhost:4317` warnings in the output — these come from the OTel exporter retrying against a non-existent local Jaeger during the test run and are pre-existing, unrelated to this phase's changes.

- [ ] **Step 5: Final commit (if Step 1's restart left anything to record — typically a no-op)**

```bash
git status
```
Expected: working tree clean (this task is verification-only; nothing to commit unless an earlier step's command output revealed a config bug that got fixed inline, in which case `git add` + `git commit` that fix before finishing).
