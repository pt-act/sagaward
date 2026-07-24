# Requirements — Strix Governance Layer (SGL)

> Phase 1 output (Shape the Spec), spec-architect framework — same as ARTH. SGL ports
> ARTH's deterministic safety/governance plane into the **pt-act/strix** fork. Estimates in
> **iterations**, never hours/days. Traceability columns map each item to its ARTH origin
> (F#/P#) and the Strix module it touches.

---

## 1. Problem Statement

The Strix fork is a strong detection engine: type-enforced propose–dispose (`C ⊆ P`),
deterministic evidence gate, working OOB oracle, identity/diff + auth-matrix, race harness,
inventory/reachability, multi-agent graph, and a B-V2P measurement track. A code audit
(see `../agentic-redteam-harness/strix-vs-arth-assessment.md`) found its weakness is the
**deterministic safety/governance plane** — the exact plane ARTH was designed around:

- **Scope is advisory and fails open.** `host_in_scope()` returns `True` when no rules are
  set (`strix/core/inventory/collectors/_scope.py:10`) and is wired only into passive
  inventory filtering + the race dispatcher — **not** the agent's active request path
  (proxy/browser/terminal). Scope otherwise lives as a system-prompt instruction.
- **No deterministic rate limiting or credential-spray caps** (`spray.py` has payloads,
  throttling is delegated to the LLM).
- **No target-health circuit breaker / automatic kill-switch** (only manual `request_stop`).
- **No cost/budget governance** beyond `max_turns=500`; no value prioritization.
- **No cross-engagement memory** (per-run only; a good per-run redaction wall exists).

SGL adds these as a **deterministic layer that does not touch the detection engine** — the
LLM keeps proposing, the evidence gate keeps disposing; SGL only constrains *what active
actions are allowed to fire, how fast, against whom, and at what cost*, and *what knowledge
survives across engagements*.

## 2. Intent & User Value

- **Make autonomous operation safe to leave running.** Today a run needs a human watching
  because scope is advisory. SGL makes scope, rate, and blast-radius **deterministic and
  fail-closed**, so the engine can run unattended against authorized scope.
- **Do no harm to the detection engine.** SGL is **gate-neutral**: it must not change
  propose–dispose verdicts. The confirmed set for in-scope actions is byte-identical with
  or without SGL. Precision/recall of the engine is untouched.
- **Harden first, measure second.** The B-V2P / propose–dispose paper evidence is gathered
  **after** SGL lands, on the secured engine, so the published metrics reflect the system
  that will actually run. (Operator decision — see §10 sequencing.)

## 3. Primary Users & Stories

**U1 — Operator / researcher (you)**
- As an operator, I want every active action — including tools the agent shells out in the
  Kali container — to pass a fail-closed scope decision, so an unattended run physically
  cannot touch an out-of-scope asset.
- As an operator, I want a kill-switch and an automatic halt on target degradation, so a
  run that starts misbehaving stops without me.
- As a researcher, I want SGL proven gate-neutral, so reviewers cannot argue the hardening
  contaminated the propose–dispose measurements.

**U2 — Contributor**
- As a contributor, I want SGL as clean modules + middleware against the existing fork
  structure (not a rewrite), with PBT acceptance tests, so it can land as reviewable PRs.

## 4. Core Functional Requirements (the WHAT)

| ID | Capability | ARTH origin | Strix touch-point |
|----|-----------|-------------|-------------------|
| G1 | **Production sandbox image** with all pinned tools **and an egress-enforcement substrate** (default-deny + mandatory enforcing proxy that ALL container traffic traverses) | containment | `containers/`, `scripts/docker.sh`, `strix/runtime/docker_client.py` |
| G2 | **Fail-closed scope & authorization decision service** consulted by the egress substrate AND the Caido HTTP path; default-deny (fixes fail-open) | F1 / P1,P2 | new `strix/core/govern/scope.py`; `_scope.py`; `tools/proxy/` |
| G3 | **Asset-ownership attribution** (ASN/CIDR/whois confidence) feeding the scope decision | F20 / P10 | new `strix/core/govern/ownership.py`; `core/inventory/` |
| G4 | **Deterministic rate limiting + per-host budgets + credential-spray caps + lockout-aware throttle** in the egress substrate | F9 / P6 | new `strix/core/govern/limiter.py`; `core/inventory/spray.py` |
| G5 | **Target-health circuit breaker + operator kill-switch** (auto-halt on degradation) | F17 / P12 | `strix/core/agents.py` (`AgentCoordinator`) |
| G6 | **Cost/budget governor + value prioritization** (token/tool-call/spend ceilings beyond `max_turns`) | F18 / P11 | `core/inputs.py`, `core/execution.py`, `config/` |
| G7 | **Cross-engagement sanitized technique library + program-aware dedup**, extending the per-run redaction wall | F19 / F16 | `core/identity/redaction.py`, `tools/notes/`, `report/state.py` |
| G8 | **Gate-neutral integration**: SGL constrains actions only; the evidence gate and `C ⊆ P` are unchanged | (new invariant) | `core/logic/gate.py`, `core/proposals/` (read-only) |
| G9 | **Governance audit log** of every allow/deny/halt decision with reason | F12 | `telemetry/logging.py`, `report/state.py` |
| G10 | *(lower priority)* confidence/anti-loop policy + recon plateau pivot | F8 / F2,F3 | `core/execution.py`, `core/inventory/` |

## 5. Non-Functional Requirements

- **Fail-closed everywhere.** Any decision that is DENY / UNKNOWN / ERROR / expired / or
  "no scope rules loaded" blocks the action. This explicitly reverses the fork's fail-open
  default.
- **Egress completeness.** No network egress path may bypass the enforcer — shell-spawned
  tools, the browser, and Caido all traverse it. Enforced at the container boundary, not in
  the app layer alone.
- **Gate-neutrality.** SGL must not alter propose–dispose verdicts; the disposer's behavior
  is byte-identical with SGL present, for actions SGL allows.
- **Determinism of safety.** All SGL controls are deterministic code; no LLM in the
  enforcement path.
- **Reuse over rewrite.** SGL is additive modules + middleware against the v1.0.4-derived
  fork; the detection engine and upstream toolkit are untouched.
- **Observability.** Every decision logged with reason; replayable.
- **Performance.** Enforcer adds bounded per-request overhead; must not serialize the agent
  graph's parallelism beyond the configured rate budgets.

## 6. Constraints & Assumptions

- **A1 — Authorized use only.** SGL operates against signed engagement scope; it is the
  control that *enforces* it. Pre-SGL, the fork's scope is advisory.
- **A2 — Not running Strix yet.** No live runs until the production image (G1) exists and
  the scope gate (G2) is validated. The current `strix-sandbox:dev` is minimal/dev-fast.
- **A3 — Paper evidence deferred.** B-V2P metrics gathering is **out of scope for SGL** and
  happens afterward, on the secured engine (operator decision, §10).
- **A4 — LLM provider.** Inherits the fork's LiteLLM abstraction (OpenAI/Anthropic/Vertex/
  local). SGL is provider-agnostic — it sits below the model, in the action path.
- **A5 — Stack.** Python (matches the fork). PBT in **Hypothesis** (Python), not fast-check.

## 7. Existing Code / Patterns to Leverage (Reuse Before Build)

- **Caido proxy** (`tools/proxy/caido_api.py`) — the HTTP-semantics decision point.
- **Docker/Kali sandbox** (`runtime/docker_client.py`, `containers/`) — the substrate the
  egress enforcer is installed into; G1 extends this rather than replacing it.
- **`host_in_scope` + scope_rules plumbing** — generalize into the G2 decision service
  (and flip the default to fail-closed).
- **`AgentCoordinator`** (`core/agents.py`) — already has `request_stop()` /
  `cancel_descendants()` / status states; G5 hooks the breaker + kill-switch here.
- **Identity redaction** (`core/identity/redaction.py`) — the basis for the G7 sanitizer.
- **Notes/state stores** (`tools/notes/`, `report/state.py`) — extend for cross-engagement
  memory.
- **Proposal funnel / B-V2P** (`report/proposals.py`, `benchmarks/bv2p/`) — the downstream
  measurement track SGL must remain neutral to.

## 8. Out of Scope (what SGL will NOT do)

- **No changes to the detection engine** — evidence gate, propose–dispose, OOB oracle,
  identity/diff, race harness, inventory, business-logic orchestrator are untouched.
- **No B-V2P evidence gathering / paper experiments** — deferred to after SGL (§10).
- **No new attack capabilities** — SGL constrains, it does not add offense.
- **No detection-evasion, anti-forensics, or destructive payloads** — SGL is loud, logged,
  fail-closed by design.
- **No autonomous scope expansion** — ownership attribution gates assets; it does not
  authorize new ranges without operator sign-off.

## 9. Open Questions

**None.** Defaults are inherited from the ARTH locked configuration (`../agentic-redteam-harness/planning/requirements.md` §9.1):
θ=0.80, MAX_ATTEMPTS=6, per-host 10 req/s, credential cap 3/route/window, cost budget
5M tokens + 10k tool-calls, circuit-breaker 25% err / 3× p95, memory retention 90 days.
Engagement model: one at a time. All overridable per engagement.

## 10. Sequencing & relationship to the paper

```
[ G1 production image + egress substrate ]
        │
        ▼
[ G2 scope gate (fail-closed) ] ──► [ G3 ownership, G4 rate/cred, G5 breaker, G6 cost, G7 memory ]
        │
        ▼
[ G8 gate-neutrality verified ] ──► [ SGL Gate 5: secured-engine smoke on lab targets ]
        │
        ▼
  ── HOLD LINE (operator decision) ──
        │
        ▼
[ LATER: B-V2P evidence + propose–dispose paper experiments E1–E4, on the secured engine ]
```

The paper's metrics are gathered **after** the HOLD LINE, so they describe the hardened
system. SGL's job is to reach that line; the measurement track is explicitly downstream.

## 11. Quality Gate 1 (Design-Principle Alignment) — adapted

| Gate question | Assessment |
|---------------|------------|
| Enhances capability without removing human judgment? | ✅ Operator still owns scope/ROE + sign-off; SGL enforces, doesn't decide offense. |
| Glass-box / transparent? | ✅ G9 logs every decision with reason. |
| Bounds risk (authorization-first, fail-closed)? | ✅ G2 fail-closed + G1 egress completeness + G4/G5 blast-radius. |
| Does it preserve the engine's integrity? | ✅ G8 gate-neutrality is a first-class, tested invariant. |

**Gate 1: PASS** → proceed to Phase 2.
