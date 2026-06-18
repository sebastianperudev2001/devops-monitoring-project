#!/bin/bash
# security-pipeline.sh

mkdir -p security/reports

echo "=== Security Pipeline ==="

# 1. Secret detection
echo "[1/4] Scanning for secrets..."
trufflehog filesystem . --json 2>&1 | tee security/reports/trufflehog.json

# 2. SAST
echo "[2/4] Running SAST..."
semgrep --config=auto microservices/ 2>&1 | tee security/reports/semgrep.txt

# 3. Dependency scanning
echo "[3/4] Scanning dependencies..."
pip-audit -r microservices/requirements.txt 2>&1 | tee security/reports/pip-audit.txt

# 4. Container scanning
echo "[4/4] Scanning Docker images..."
for service in api-gateway auth-service data-service; do
  docker build -t security-pipeline/${service}:scan -f microservices/Dockerfile.${service} microservices
  trivy image security-pipeline/${service}:scan --severity HIGH,CRITICAL 2>&1 | tee security/reports/trivy-${service}.txt
done

echo "=== Security scan complete ==="
