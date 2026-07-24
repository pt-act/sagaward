# Spec — Strix Governance Layer (SGL)

Implements ARTH's deterministic safety/governance plane **inside the pt-act/strix fork** as
an additive layer, so the engine can run autonomously against authorized scope without a
human watching — while leaving the detection engine and its propose–dispose verdicts
byte-identical. Built with the **spec-architect** framework (same 4 phases + Gates 1–5 used
for ARTH).

## Read in this order

| Phase | Document | Covers |
|-------|----------|--------|
| 1 — Shape | [`planning/requirements.md`](planning/requirements.md) | Problem (audited gaps), G1–G10 functional reqs with ARTH→Strix traceability, NFRs, reuse, out-of-scope, sequencing, Gate 1 (PASS). |
| 2 — Write | [`spec.md`](spec.md) | Egress-enforcement architecture, AC-G1–G9, component contracts mapped to fork files, SP1–SP10, gate-neutrality invariant, Gates 1–5. |
| 3 — Tasks | [`tasks.md`](tasks.md) | S0–S8 groups, dependency graph, critical path, 3-track parallelization, tiered validation, ~22/~14 iteration estimates. |
| 4 — Validate | [`pbt-properties.py`](pbt-properties.py) · [`security-audit-prep.md`](security-audit-prep.md) | Hypothesis properties SP1–SP10 + Gate-4 audit + Gate-5 HOLD LINE. |

## The two ideas that make SGL fit Strix specifically

1. **Enforce at the container egress boundary, not just Caido.** The agent shells out
   (nmap/sqlmap/nuclei/curl) and drives a browser, so a Caido-only gate can't be fail-closed.
   The egress enforcer (default-deny + mandatory proxy) makes scope fail-closed for the
   *whole* agent — this is why the production Docker image (S0) is the foundation, not a
   side task. Property **SP3 (egress completeness)** guards it.
2. **Gate-neutrality.** SGL may only *remove actions upstream*; it never alters a
   disposition. The confirmed-finding set is byte-identical with/without SGL, and SGL
   imports nothing from the detection-engine packages. Property **SP8** guards it — and it
   is what keeps the propose–dispose paper's metrics uncontaminated.

## ARTH → SGL → Strix mapping

| ARTH feature | SGL group | Strix touch-point |
|--------------|-----------|-------------------|
| Fail-closed scope gate (F1/P1,P2) | S1 | `govern/scope.py` (generalizes `_scope.py`, flips fail-open→fail-closed) |
| Ownership attribution (F20/P10) | S2 | `govern/ownership.py` + `core/inventory/` |
| Rate / credential guardrails (F9/P6) | S2 | `govern/limiter.py` + `core/inventory/spray.py` |
| Circuit breaker + kill-switch (F17/P12) | S3 | `core/agents.py` (`AgentCoordinator`) |
| Cost / value governor (F18/P11) | S4 | `core/inputs.py`, `core/execution.py`, `config/` |
| Cross-engagement memory + dedup (F19/F16) | S5 | `tools/notes/`, `report/state.py`, `core/identity/redaction.py` |
| Production sandbox + egress substrate (containment) | S0 | `containers/`, `runtime/docker_client.py`, `scripts/docker.sh` |

Retired from ARTH: the dual-model **LLM Skeptic** — the fork's deterministic, type-enforced
evidence gate is a strictly better disposer and SGL leaves it untouched.

## Sequencing (operator decision)

```
S0 image+egress → S1 scope(fail-closed) → S2/S3/S4/S5/S6 → S7 integrate → S8 gate-neutrality + Gate 5 HOLD LINE
                                                                                   │
                                                              ── then, separately ──▼
                                          B-V2P evidence + propose–dispose paper experiments E1–E4 (hardened engine)
```

No live runs until S0 exists and S1 is validated. Paper evidence is **deferred** until after
the Gate 5 HOLD LINE, so the published metrics describe the secured system.

## Estimate
~22 iterations sequential, ~14 across 3 tracks. S0 (production image + egress substrate) and
S1 (fail-closed scope) — the two audited safety gaps — are built first.

## Status: SPEC — ready for go
Zero-tolerance release properties: **SP1, SP2, SP3, SP6, SP8.** Next on go: S0 → S1.
