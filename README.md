# DevOps Monitoring Project

Proyecto final de un curso de DevOps y Observabilidad de 3 días. Consiste en un stack completo de monitoreo para tres microservicios Flask dockerizados, con métricas, logs, trazas distribuidas, alertas y un pipeline de seguridad. El trabajo está dividido en 8 fases, de las cuales 5 están completadas y 3 quedan pendientes.

## Descripción

El sistema expone tres microservicios Flask detrás de un API Gateway con autenticación JWT y rate limiting. Toda la actividad de los servicios se observa a través de un stack basado en Prometheus, Loki, Jaeger y Grafana, orquestado con Docker Compose. Adicionalmente, un pipeline de seguridad ejecuta escaneos de secretos, SAST, vulnerabilidades de dependencias e imágenes Docker.

## Arquitectura

### Microservicios

Los tres microservicios viven en `microservices/` y comparten el módulo `microservices/common/`, que provee logging estructurado (con `request_id`) y tracing con OpenTelemetry hacia Jaeger vía OTLP. Cada servicio tiene su propio Dockerfile y sus tests en `microservices/tests/`.

| Servicio | Puerto | Responsabilidad | Endpoints |
| --- | --- | --- | --- |
| `api-gateway` | 5000 | Punto de entrada único. Valida que las peticiones a `/api/data` lleven un token Bearer válido (consultando a `auth-service`) y luego solicita los datos a `data-service`. Incluye rate limiting de ventana deslizante. | `GET /api/data`, `GET /health`, `GET /metrics` |
| `auth-service` | 5001 | Emite y valida JWT. Usuario demo: `demo` / `demo123`. | `POST /login`, `GET /validate`, `GET /health`, `GET /metrics` |
| `data-service` | 5002 | Sirve los datos de negocio. | `GET /data`, `GET /health`, `GET /metrics` |

El rate limiting del `api-gateway` es configurable mediante las variables de entorno `RATE_LIMIT` y `RATE_LIMIT_WINDOW_SECONDS` (valor por defecto: 20 peticiones por cada 10 segundos).

### Stack de observabilidad

El stack se orquesta con `docker-compose.yml` (en la raíz del repo) y levanta 9 contenedores en total.

| Componente | Puerto | Función |
| --- | --- | --- |
| Prometheus | 9090 | Scrapea las métricas de los tres microservicios cada pocos segundos. Configuración y reglas en `observability/prometheus/`. |
| Alertmanager | 9093 | Recibe las alertas de Prometheus y las rutea a Slack (webhook placeholder en `observability/alertmanager/secrets/`). |
| Loki | 3100 | Almacena los logs. No tiene UI propia; se consulta desde Grafana. |
| Promtail | (sin puerto público) | Recolecta los logs de todos los contenedores Docker vía el socket de Docker y los empuja a Loki. |
| Jaeger | 16686 (UI), 4317 (OTLP) | Trazas distribuidas. Muestra el viaje de una petición a través de los tres microservicios. |
| Grafana | 3000 | Visualización. Login: `admin` / `admin`. Dashboards provisionados en `observability/grafana/dashboards/`. |

#### Reglas de Prometheus

- `observability/prometheus/rules/recording-rules.yml`: 9 reglas (las 3 señales doradas por cada uno de los 3 servicios).
- `observability/prometheus/rules/alert-rules.yml`: 6 alertas.

#### Dashboards de Grafana

| Dashboard | UID |
| --- | --- |
| Service Overview | `service-overview` |
| Logs | `logs-dashboard` |
| Security | `security-dashboard` |
| Business Metrics | `business-metrics` |

## Cómo levantar el proyecto

```bash
docker compose up -d --build
```

Espera a que todos los healthchecks pasen:

```bash
docker compose ps
```

### Nota para macOS

En algunos Mac, Control Center (AirPlay Receiver) ocupa el puerto 5000 por defecto, lo cual choca con `api-gateway`. Si `docker compose up` falla con `address already in use` en el puerto 5000, desactiva AirPlay Receiver en `Configuración del Sistema -> General -> AirDrop y Handoff` y luego ejecuta:

```bash
killall ControlCenter
```

## URLs y puertos

Una vez levantado el stack:

```text
http://localhost:5000/health    # api-gateway (solo responde JSON)
http://localhost:5001/health    # auth-service (solo responde JSON)
http://localhost:5002/health    # data-service (solo responde JSON)

http://localhost:3000           # Grafana (admin/admin)
http://localhost:9090           # Prometheus UI
http://localhost:9093           # Alertmanager UI
http://localhost:16686          # Jaeger UI
http://localhost:3100           # Loki (sin UI, solo API; se consulta desde Grafana)
```

Links directos a los dashboards de Grafana:

```text
http://localhost:3000/d/service-overview
http://localhost:3000/d/logs-dashboard
http://localhost:3000/d/security-dashboard
http://localhost:3000/d/business-metrics
```

## Cómo generar tráfico de prueba

Para que los dashboards muestren datos, genera algo de tráfico:

```bash
# Login fallido (señal de seguridad)
curl -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"wrong"}'

# Login real, capturando el token
TOKEN=$(curl -s -X POST http://localhost:5001/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Tráfico autenticado a través del gateway
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/data
```

## Seguridad

El pipeline de seguridad se ejecuta con:

```bash
./security-pipeline.sh
```

Requiere tener instalados localmente `trufflehog`, `semgrep`, `pip-audit` y `trivy`, además de Docker corriendo. El script ejecuta 4 escaneos y guarda el output crudo en `security/reports/` (no genera un reporte interpretado; esta es una decisión de alcance explícita):

1. `trufflehog` — detección de secretos.
2. `semgrep --config=auto` — SAST (análisis estático de código).
3. `pip-audit` — vulnerabilidades en las dependencias de `requirements.txt`.
4. `trivy image` — vulnerabilidades en las 3 imágenes Docker construidas (severidad HIGH/CRITICAL).

### Hallazgos reales documentados

- 1 CVE CRITICAL en `perl-base`.
- 5 CVE HIGH en `PyJWT`.

Estos hallazgos están presentes en las imágenes de los tres servicios.

## Estado del proyecto

| Fase | Descripción | Estado |
| --- | --- | --- |
| 1 | Microservicios core | Completado |
| 2 | Stack de observabilidad (docker-compose) | Completado |
| 3 | Reglas y alertas de Prometheus | Completado |
| 4 | Dashboards de Grafana | Completado |
| 5 | Pipeline de seguridad | Completado |
| 6 | CI/CD (GitHub Actions: tests + pipeline de seguridad + build de imágenes) | No iniciado |
| 7 | Kubernetes + Helm + Istio (service mesh con tracing automático) | No iniciado |
| 8 | Documentación y respuestas de reflexión | No iniciado |

## Limitaciones conocidas

En el dashboard de Security de Grafana, los paneles **Auth Error Breakdown**, **CVEs Detected** y **Security Score** muestran permanentemente `No data`. Esto no es un bug.

Esos paneles fueron diseñados anticipando un exportador de métricas de seguridad (por ejemplo `security_vulnerabilities_total` o `security_score`) que la fase de seguridad finalmente no construyó: su entregable fueron archivos de texto crudo en `security/reports/`, no un exporter de Prometheus. Tampoco existe un `node_exporter` ni un `Pushgateway` en el `docker-compose.yml`.

Se trata de un contrato entre fases que quedó sin satisfacer. Se documenta así para que quien lea el repo no pierda tiempo intentando depurar algo que no es un error.
