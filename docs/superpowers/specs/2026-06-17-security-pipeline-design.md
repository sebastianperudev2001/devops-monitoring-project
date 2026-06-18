# Phase 5: Security Pipeline — Design Spec

**Status:** Approved
**Date:** 2026-06-17
**Phase:** 5 of 8 (see Project Roadmap in `docs/superpowers/specs/2026-06-17-microservices-core-design.md`)

## Context

Phases 1–3 (microservices, observability stack, Prometheus rules/alerting) are complete. This phase
covers the course's "Seguridad" requirement: a `security-pipeline.sh` running secret detection (trufflehog),
SAST (semgrep), dependency scanning (pip-audit), and container scanning (trivy), plus documentation of at
least one real finding. The course gives a literal 4-step script template (`echo` headers + one tool
invocation per step); this phase adapts that template to actually run against this repo's real code and
images rather than the template's placeholder `myapp:latest`.

## Goals

- `security-pipeline.sh` at the repo root, runnable standalone, executing all 4 tools for real against
  this repo.
- Each tool's raw output saved to `security/reports/`, committed to git — this raw output *is* the
  deliverable "Reporte de vulnerabilidades encontradas," not a separately authored summary.
- At least one real, safe-to-publish finding captured (the known hardcoded JWT fallback secret / demo
  password in `auth_service.py`), satisfying the rubric's "≥1 vulnerability identified and documented."
- Container scanning covers all 3 service images (api-gateway, auth-service, data-service), each built
  inline by the script with an explicit tag — no dependency on `docker-compose` being up, no edits to
  `docker-compose.yml`.

## Non-goals (deferred to later phases / explicitly out of scope)

- CI/CD wiring (calling this script from GitHub Actions, gating a build on its findings) → Phase 6.
- Grafana "Security" dashboard with CVE metrics → Phase 4 (bonus scope).
- A separately authored vulnerability report or remediation plan document. Raw tool output is the only
  artifact for this phase, by explicit choice — accepted that this is a thinner deliverable than the
  course's "Plan de remediación" line technically asks for, given this phase is 5% of the total grade.
- Auto-installing the 4 scanning tools from inside the script. None of trufflehog/semgrep/pip-audit/trivy
  are installed on this machine today; they're installed manually (via `brew`/`pip3`) once, as a
  verification step for this phase, not as script logic — the course's own template has no install
  logic either.

## The 4 pipeline steps

`security-pipeline.sh`, no `set -e`: each tool's "findings found" exit code (semgrep, pip-audit, and
trufflehog all exit non-zero when they find something) must not abort later steps. The script always
runs all 4 steps and ends with `=== Security scan complete ===`, exiting 0 — this script reports, it
doesn't gate; gating policy is Phase 6's decision.

| # | Step | Command | Output file |
|---|------|---------|---|
| 1 | Secret detection | `trufflehog filesystem . --json` | `security/reports/trufflehog.json` |
| 2 | SAST | `semgrep --config=auto microservices/` | `security/reports/semgrep.txt` |
| 3 | Dependency scanning | `pip-audit -r microservices/requirements.txt` | `security/reports/pip-audit.txt` |
| 4 | Container scanning (×3) | build + `trivy image <tag> --severity HIGH,CRITICAL` | `security/reports/trivy-<service>.txt` |

Each command's stdout+stderr is piped through `tee` to its report file, so output is visible live in the
terminal and persisted at the same time.

Step 4 detail, run once per service (`api-gateway`, `auth-service`, `data-service`):
```bash
docker build -t security-pipeline/<service>:scan -f microservices/Dockerfile.<service> microservices
trivy image security-pipeline/<service>:scan --severity HIGH,CRITICAL
```
Building the image inline with a fixed, predictable tag avoids relying on `docker-compose`'s
auto-generated image names (which vary with the parent directory name and Compose version) and means the
script works whether or not the observability stack is currently running.

Step 2 is scoped to `microservices/` rather than the whole repo so semgrep's `--config=auto` ruleset
(Python/Flask-aware) isn't spent on Markdown docs, YAML configs, or `docs/superpowers/` plan/spec files
that aren't application code.

### Why these specific choices

- **Raw output committed as-is, no aggregation script.** Turning 4 tools' differently-shaped output into
  one normalized report (e.g. one combined JSON, a generated Markdown summary) was considered and
  rejected for this phase — explicit user choice, given the phase's small grading weight (5% total: 3%
  "script executed," 2% "≥1 vulnerability documented"). The raw files already satisfy both rubric lines
  once at least one real finding is in them.
- **JSON only for trufflehog, plain text for the other three.** This matches the course's own literal
  template, which only specifies `--json` for trufflehog; semgrep/pip-audit/trivy use their default
  human-readable output in the template. Keeping that default makes the saved `.txt` files actually
  readable as "documented" evidence, rather than three more JSON blobs needing a parser to inspect.
- **The expected JWT-secret/demo-password finding is safe to commit.** `auth_service.py`'s
  `JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")` and `DEMO_PASSWORD = "demo123"` are
  intentional Phase-1 placeholders (already a known, accepted trade-off, not a real credential), so
  trufflehog/semgrep flagging them and that finding landing in committed report files carries no real
  secret-leak risk.
- **No tool-presence checks in the script.** The course's own template calls each tool directly with no
  `command -v` guard; matching that keeps the script as close to the literal course deliverable as
  possible. Tool installation is a one-time manual setup step for whoever runs this, documented in the
  implementation plan's verification section, not script logic.

## File layout

```
security-pipeline.sh                          # NEW, repo root
security/
└── reports/
    ├── trufflehog.json                        # NEW
    ├── semgrep.txt                             # NEW
    ├── pip-audit.txt                           # NEW
    ├── trivy-api-gateway.txt                   # NEW
    ├── trivy-auth-service.txt                  # NEW
    └── trivy-data-service.txt                  # NEW
```

No other phase's files are touched (no changes to `docker-compose.yml`, `observability/`, or
`microservices/` application code).

## Testing / Verification (for the implementation plan)

1. Install the 4 tools locally (`brew install trufflehog semgrep aquasecurity/trivy/trivy`, `pip3 install
   pip-audit`), since none are present on this machine today.
2. `chmod +x security-pipeline.sh && ./security-pipeline.sh` from the repo root — confirm all 4 steps run
   to completion (script reaches "Security scan complete" regardless of individual tool exit codes) and
   all 6 report files are created and non-empty.
3. Inspect `security/reports/trufflehog.json` and/or `security/reports/semgrep.txt` for the expected
   `dev-secret-change-me` / `DEMO_PASSWORD` finding — confirms the "≥1 vulnerability identified and
   documented" rubric line is satisfied with a real, reproducible finding.
4. Spot-check `security/reports/trivy-*.txt` for HIGH/CRITICAL OS or Python package CVEs in the built
   images (base image `python:3.11-slim`, per the existing Dockerfiles).

## Known Limitations (Accepted for This Phase's Scope)

- **No remediation plan document.** The course's deliverables list names one explicitly; this phase
  produces raw scan output only, by explicit user choice given the phase's small grading weight.
- **No CI gating.** The script always exits 0 regardless of findings; whether/how Phase 6 should fail a
  build on HIGH/CRITICAL findings is that phase's decision, not predetermined here.
- **Tool versions are whatever `brew`/`pip3` resolve to at install time**, not pinned — acceptable for a
  one-time local/teaching run; a real CI pipeline would pin scanner versions for reproducible results.
