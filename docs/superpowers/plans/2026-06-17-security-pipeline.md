# Phase 5: Security Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable `security-pipeline.sh` that executes trufflehog, semgrep, pip-audit, and trivy for real against this repo, with each tool's raw output saved under `security/reports/` as the committed deliverable.

**Architecture:** A single bash script with no `set -e`, run from the repo root. Each of the course's 4 named steps invokes one tool and tees its output to a dedicated report file. Container scanning builds each of the 3 service images inline with a fixed tag before scanning, so the script never depends on `docker-compose` being up.

**Tech Stack:** bash, trufflehog, semgrep, pip-audit, trivy, docker.

## Global Constraints

- No `set -e` in the script — every tool's non-zero "findings found" exit code must not abort later steps; the script always reaches `=== Security scan complete ===` and exits 0.
- Step 2 (semgrep) is scoped to `microservices/` only, not the whole repo.
- Step 4 (trivy) builds each image inline as `security-pipeline/<service>:scan` via `docker build -f microservices/Dockerfile.<service> microservices` — no edits to `docker-compose.yml`.
- Only trufflehog uses `--json`; semgrep/pip-audit/trivy use their default human-readable output, matching the course's literal template.
- No separately authored report or remediation-plan document — the raw files under `security/reports/` are the only deliverable for this phase (explicit scope decision in the design spec).
- No CI wiring in this script (Phase 6's scope).

---

### Task 1: Write `security-pipeline.sh`

**Files:**
- Create: `security-pipeline.sh`

**Interfaces:**
- Produces: an executable script at the repo root, runnable as `./security-pipeline.sh` from the repo root, that creates `security/reports/{trufflehog.json,semgrep.txt,pip-audit.txt,trivy-api-gateway.txt,trivy-auth-service.txt,trivy-data-service.txt}` when run. Task 2 depends on this script existing and matching this exact structure.

- [ ] **Step 1: Write the script**

```bash
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
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x security-pipeline.sh`

- [ ] **Step 3: Verify the script's syntax**

Run: `bash -n security-pipeline.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK` printed, no error output. This only checks parsing — the 4 tools aren't installed yet, so a real run happens in Task 2.

- [ ] **Step 4: Verify the 4-step structure is intact**

Run: `grep -c '^echo "\[' security-pipeline.sh`
Expected: `4` (one `[n/4]` progress echo per step — catches an accidental dropped step before Task 2's real run).

- [ ] **Step 5: Commit**

```bash
git add security-pipeline.sh
git commit -m "feat: add security-pipeline.sh running trufflehog/semgrep/pip-audit/trivy"
```

---

### Task 2: Install the scanning tools and run the pipeline for real

**Files:**
- Create: `security/reports/trufflehog.json`
- Create: `security/reports/semgrep.txt`
- Create: `security/reports/pip-audit.txt`
- Create: `security/reports/trivy-api-gateway.txt`
- Create: `security/reports/trivy-auth-service.txt`
- Create: `security/reports/trivy-data-service.txt`

**Interfaces:**
- Consumes: `security-pipeline.sh` from Task 1, run unmodified.
- Produces: the 6 committed report files above — the phase's actual deliverable.

- [ ] **Step 1: Install the 4 tools**

None of trufflehog, semgrep, pip-audit, or trivy are installed on this machine yet (all core Homebrew formulas, confirmed via `brew info`).

Run: `brew install trufflehog semgrep trivy pip-audit`
Expected: brew reports each as installed (or already installed/up to date) with exit code 0.

- [ ] **Step 2: Verify each tool is callable**

Run: `trufflehog --version && semgrep --version && pip-audit --version && trivy --version`
Expected: each prints a version string, no "command not found" errors.

- [ ] **Step 3: Run the pipeline**

Run (from repo root): `./security-pipeline.sh; echo "EXIT_CODE=$?"`
Expected: all 4 `[n/4]` progress lines print in order, the script reaches `=== Security scan complete ===`, and `EXIT_CODE=0` — regardless of whether individual tools reported findings (their non-zero exit codes are swallowed by the absence of `set -e` and by piping through `tee`).

- [ ] **Step 4: Verify all 6 report files exist and are non-empty**

Run: `wc -l security/reports/*`
Expected: 6 files listed, none with `0` lines. (`trivy-*.txt` will contain at minimum a scan summary/table header even with zero matching CVEs; the other 3 print step banners and findings or a "no issues found"-style line.)

- [ ] **Step 5: Confirm at least one real, documentable finding**

Run: `grep -l -i "HIGH\|CRITICAL" security/reports/trivy-*.txt; grep -rn -i "dev-secret-change-me\|DEMO_PASSWORD" security/reports/`
Expected: at least one match from either command. `python:3.11-slim` (the base image for all 3 services, per `microservices/Dockerfile.*`) very commonly carries at least one HIGH/CRITICAL OS-package CVE, which is the most reliable source of the rubric's "≥1 vulnerability identified" — the hardcoded `dev-secret-change-me`/`DEMO_PASSWORD` strings in `microservices/auth_service.py` are a secondary candidate if semgrep's ruleset flags them. If neither command matches anything, do not fabricate a finding — re-run step 3 and inspect the full report files manually; it's fine for this task to take an extra iteration to confirm real output before moving on.

- [ ] **Step 6: Commit the report files**

```bash
git add security/reports/
git commit -m "chore: run security pipeline, commit trufflehog/semgrep/pip-audit/trivy reports"
```

---

## Self-Review Notes

- **Spec coverage:** all 4 steps from the design spec are implemented in Task 1; Task 2 covers the spec's "Testing / Verification" section items 1–4 (tool install, full run, report files non-empty, real finding present) plus the spec's safety note that the expected secret finding is safe to commit.
- **No placeholders:** every step has literal commands and exact expected output; Step 5 of Task 2 explicitly avoids the "fabricate a finding" trap by naming the most likely real source (base-image CVEs) instead of assuming a specific tool catches the demo secret.
- **Non-goals respected:** no task adds a remediation doc, an aggregated report, or any CI file — matching the spec's explicit scope cuts.
