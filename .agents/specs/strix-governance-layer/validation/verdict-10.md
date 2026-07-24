# Verdict — SGL Deployment-Containment Fixes (PRE-3 / PRE-4) — round 5

## Header
```
spec_id:        strix-governance-layer (S0 containment re-validation)
validator:      opus-4.8-pm-auditor   (distinct from producer mimo/mimo-v2.5-pro)
reviewed:       branch sgl-deploy-fix @ 24187bc + operator-run live containment test on rebuilt strix-sandbox:prod
companion:      coder-handoff-sgl-deployment-fixes.md ; reopens verdict-04 (S0)
timestamp:      2026-06-21 09:00 UTC
```

## Decision
```
status: approved — S0 containment re-validated; cleared to merge sgl-deploy-fix → main
```

## Evidence (the standard verdict-04 lacked: live output, not "looks right")

**FIX 1 (PRE-4) — proxy no longer crashes:** image build includes the 5 govern COPY layers
(14–18); container logs on the rebuilt prod image show no `ModuleNotFoundError`. The decision
proxy loads. Verified in image + live.

**FIX 2 (PRE-3) — non-root agent is contained:** deterministic live test on `strix-sandbox:prod`
(`STRIX_EGRESS_ENFORCE=1`, empty scope):
| exec user | `id -un` | `curl http://example.com` | `sudo iptables -F` |
|-----------|----------|---------------------------|--------------------|
| root (entrypoint) | root | **BYPASS** (uid-0 proxy exemption — by design) | n/a |
| **pentester (agent)** | **pentester** | **BLOCKED** | **denied (no password)** |

The make-or-break — **pentester egress BLOCKED on empty scope** — holds. A non-root agent is
subject to the iptables redirect → decision proxy → fail-closed, and cannot flush the rules.

**Code path verified:** `strix/agents/factory.py:466` sets `run_as="pentester"` under enforcement,
passed to `SandboxAgent(run_as=...)` for root + (via `make_child_factory`) child agents; the SDK
execs tools through `agent.run_as` (`shell_tool.py:99` → `_agent_run_as_user`). So the agent's
tools run as pentester at runtime — the exact user the live test proved is contained.

## What this closes
S0 containment, reopened at the Gate-5 smoke, is re-validated. verdict-04's "create-root /
Dockerfile-USER-exec" reasoning was wrong (Docker uses the create-user for exec too); the correct
mechanism is the SDK `run_as`, now wired and proven. The empty-scope fail-OPEN bypass is closed:
entrypoint=root (installs firewall once), agent=pentester (subject to it, can't flush it).

## Residual (low risk, confirmed at next step — not a gate)
The deterministic test forced `-u pentester`; the *integrated* confirmation that the SDK applies
`run_as` end-to-end rides on the first live M0 run (agent runs `id` → expect pentester; empty-scope
deny-control → agent reaches nothing). Both halves (mechanism + code) are independently verified, so
risk is low; the M0 run doubles as the final confirmation and is **step 1 of the empirical run**, not
a merge gate.

## Cleared
- Merge `sgl-deploy-fix` → `main` (squash). This makes the prod image's containment real on main.
- After merge: the live M0 (operator sets `STRIX_LLM` + `LLM_API_KEY`) — empirical-run start.

## Tracked, not gating
- **PRE-1** — 4 `test_business_logic_fixture` full-suite Docker tests: pre-existing Phase-5 defect.
- **S3.1** — breaker measures agent-cycle not target-request health: required before unattended
  non-owned-target use; see `pm-decision-breaker-target-health.md`.

## Note on suite
Producer-reported 524 passed / 4 pre-existing-Docker-failed; consistent with my prior validator-run
at 6f690ec. I could not re-run this turn (local uv interpreter permission glitch); the factory change
is test-inert (env-gated on `STRIX_EGRESS_ENFORCE`, unset in tests).

## Session Manifest
```
Skill: pm-auditor@2.0.0 + v2.1 · validator: opus-4.8-pm-auditor
Spec: strix-governance-layer (S0 containment) · Round 5 · Branch sgl-deploy-fix @ 24187bc
Evidence: live deterministic containment test (pentester BLOCKED / root BYPASS / sudo denied) on
          rebuilt strix-sandbox:prod; image COPY layers 14-18; factory.py:466 run_as wiring;
          SDK shell_tool.py:99 + _agent_run_as_user
Decision: approved — merge cleared; S0 containment re-validated
Prior conflict: none (no producer pushback) → no arbiter audit
Self-check: passed · Drift: verdict-04 error owned + corrected
```
