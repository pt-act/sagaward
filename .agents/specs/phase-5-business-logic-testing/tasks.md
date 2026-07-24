# Phase 5 — Business-Logic State Testing — Tasks

> Spec-Architect PBT variant · Primitives **P1 + P2 + P3 + F3 + Phase-4 race harness** · Feature **F5**.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.
> **Hard dependency:** Phases 1–4 must be landed — Phase 5 consumes P1 (replay), P2 (diff), P3 (callback), the Phase-4 race harness, and the Phase-3 inventory. It is the terminal phase and is not schedulable before them.

---

## Overview

Six task groups build the terminal feature: an agent-proposed **journey/state model intake**, a fixed **invariant catalog & violation-test library**, an **execution orchestrator** that wires P1/P2/P3/P4, the **evidence gate** (the hard noise control), **report integration** (impact-gated), and **testing**. Critical path is `model intake → catalog/tests → orchestrator → evidence gate → report → testing`. The **evidence gate + no-self-confirmation PBT develop in parallel** against synthetic (model, executed-sequence, artifact) fixtures while the orchestrator is wired. Total focused tests: **27** (within 16–34). Target: **~9 iterations**.

---

## Task Group 1 — Journey / State-Model Intake (agent-proposed schema)

### Implementation
- [ ] 1.1 Define the agent-proposed model schema: journeys (ordered steps), object lifecycles (states + allowed transitions), trust boundaries (identity ↔ step), monetary operations (amount/price/quantity relations), named flows (approval/coupon/refund/credit/invite) (not_started)
- [ ] 1.2 Durable per-engagement model store, mirroring `strix/core/sessions.py` SQLite pattern; path via `strix/core/paths.py` (not_started)
- [ ] 1.3 Tag every model field `agent-proposed`; reference endpoints/params from the Phase-3 inventory (param classes `amount`/`state`/`role`) instead of re-deriving (not_started)

### Validation Tier 1: Focused Testing
- [ ] 1.4 Model submit → read round-trip; survives restart (1 test) (not_started)
- [ ] 1.5 Every model field carries the `agent-proposed` tag; none is auto-trusted (1 test) (not_started)
- [ ] 1.6 Model references Phase-3 inventory params (does not re-derive surface) (1 test) (not_started)

### Security Readiness Checklist
- [ ] 1.7 Model store is per-engagement scoped; no cross-target read path (not_started)
- [ ] 1.8 Proposed fields are never readable as confirmed findings (hypothesis isolation seam) (not_started)

---

## Task Group 2 — Invariant Catalog & Violation Tests (deterministic)

### Implementation
- [ ] 2.1 Fixed invariant catalog enumerating violation *kinds*: step-skip, replay, double-spend/race, quantity/price-mismatch, unauthorized-state-change (not_started)
- [ ] 2.2 Step-skip test: reach step N without N−1, replayed as the modeled identity (P1) (not_started)
- [ ] 2.3 Replay test: re-submit a one-time action (coupon/token/approval) a second time (not_started)
- [ ] 2.4 Quantity/price-mismatch test: tamper amount/price/quantity (Phase-3 `amount` params), re-derive expected total, replay as buyer (P1) (not_started)
- [ ] 2.5 Unauthorized-state-change test: drive a model-forbidden transition as a non-permitted identity (P1); async variant via callback (P3) (not_started)
- [ ] 2.6 Double-spend test: delegate concurrent redemption to the **Phase-4 race harness** (no new concurrency code) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 2.7 Step-skip test flags a candidate on a seeded out-of-order fixture (1 test) (not_started)
- [ ] 2.8 Price-mismatch test flags a candidate when charged total contradicts the model relation (1 test) (not_started)
- [ ] 2.9 Unauthorized-transition test flags a forbidden transition that succeeds (1 test) (not_started)
- [ ] 2.10 Double-spend test invokes the Phase-4 harness and surfaces its state-delta (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 2.11 PBT — **invariant-violation soundness**: every flag is an executed sequence reaching a model-declared-impossible state (not_started)

### Security Readiness Checklist
- [ ] 2.12 Catalog is fixed/enumerable; the test for a kind is identical every run (no model output in test logic) (not_started)

---

## Task Group 3 — Execution Orchestrator (wires P1/P2/P3/P4)

### Implementation
- [ ] 3.1 Orchestrator entry per invariant kind: dispatch (flow, invariant_kind) → the right violation test (not_started)
- [ ] 3.2 Wire **P1** replay-as-identity for stepped/identity-driven tests; wire **P2** before/after diff capture (not_started)
- [ ] 3.3 Wire **P3** mint/await-callback for async/webhook transitions; wire the **Phase-4 race harness** for double-spend (not_started)
- [ ] 3.4 Record the full executed sequence + resulting state for reproduction (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.5 Orchestrator drives a step sequence via P1 and captures a P2 diff artifact (1 test) (not_started)
- [ ] 3.6 Orchestrator delegates double-spend to the Phase-4 harness and captures its race-result artifact (1 test) (not_started)
- [ ] 3.7 Executed sequence is recorded and re-runnable (reproduction substrate) (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 3.8 PBT — **primitive-reuse fidelity**: double-spend → Phase-4 harness; identity steps → P1 (no re-implemented concurrency/replay) (not_started)

### Security Readiness Checklist
- [ ] 3.9 Orchestrator emits only typed artifacts (diff/callback/race-result), never model rationale (not_started)
- [ ] 3.10 No concurrency/replay/diff/callback logic duplicated from Phases 1–4 (not_started)

---

## Task Group 4 — Evidence Gate (hard control)  *(parallel: develops against fixtures)*

### Implementation
- [ ] 4.1 Gate accepts a violation iff a deterministic artifact (P2 diff ∨ P3 callback ∨ Phase-4 race result) is attached (not_started)
- [ ] 4.2 Gate additionally requires the executed sequence reached a state the model declared impossible (not_started)
- [ ] 4.3 Gate rejects free-text / narrative rationale as evidence; the proposing model is excluded from the confirmation path (not_started)
- [ ] 4.4 Reproducibility check: re-run the harness; confirm the same disallowed state before promotion (not_started)

### Validation Tier 1: Focused Testing
- [ ] 4.5 Candidate **with** a diff artifact AND model-impossible state → confirmed (1 test) (not_started)
- [ ] 4.6 Candidate **without** any artifact → suppressed (stays unconfirmed hypothesis) (1 test) (not_started)
- [ ] 4.7 Candidate whose state is actually allowed by the model → not confirmed (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 4.8 PBT — **evidence-gated reporting**: `∀ reported v: v carries a P2 diff ∨ P3 callback ∨ Phase-4 race result` (not_started)
- [ ] 4.9 PBT — **no self-confirmation**: `∀ proposed I: confirmation(I)` originates from a harness, never the proposing model (not_started)
- [ ] 4.10 PBT — **reproducibility**: `∀ reported v: re-running v's harness reproduces the disallowed state` (not_started)

### Security Readiness Checklist
- [ ] 4.11 No code path lets a model proposal self-promote without a typed artifact (not_started)
- [ ] 4.12 Hypothesis isolation: `agent-proposed` fields never cross into confirmed without passing the gate (not_started)

---

## Task Group 5 — Report Integration & Agent Tool Surface (F5)

### Implementation
- [ ] 5.1 `@function_tool` model intake (submit/read), list-invariants-for-flow, run-violation, read-gated-result — mirroring `strix/tools/proxy` (`_ctx_client`, JSON returns) (not_started)
- [ ] 5.2 Confirmed violation → `add_vulnerability_report` (`strix/report/state.py`) carrying violated invariant + executed sequence (reproduction) + backing artifact (not_started)
- [ ] 5.3 Suppress reporting for unconfirmed hypotheses; surface them as explicit unconfirmed results, never as findings (not_started)

### Validation Tier 1: Focused Testing
- [ ] 5.4 Run-violation tool returns confirmed-with-evidence vs unconfirmed-hypothesis correctly (1 test) (not_started)
- [ ] 5.5 Confirmed report carries reproduction + artifact; unconfirmed never reaches `vulnerability_reports` (1 test) (not_started)

### Security Readiness Checklist
- [ ] 5.6 Report bodies carry the artifact, never the model's narrative rationale as proof (not_started)
- [ ] 5.7 Tool returns keep proposed vs confirmed visibly separated (not_started)

---

## Task Group 6 — Testing (integration & gap-fill)

### Validation Tier 1: Focused Testing
- [ ] 6.1 End-to-end double-spend: model coupon → run via Phase-4 harness → race-result gate → confirmed report on a seeded target (1 test) (not_started)
- [ ] 6.2 End-to-end price-mismatch: model price relation → tamper+replay (P1) → diff (P2) gate → confirmed report (1 test) (not_started)
- [ ] 6.3 End-to-end unauthorized-transition: forbidden transition as low-priv identity (P1) → diff gate → confirmed report (1 test) (not_started)
- [ ] 6.4 Negative end-to-end: plausible-but-wrong invariant proposed, no artifact produced → nothing reported (confirmation-bias guard) (1 test) (not_started)

### Security Readiness Checklist
- [ ] 6.5 Full PBT suite (2.11, 3.8, 4.8, 4.9, 4.10) green before audit gate (not_started)
- [ ] 6.6 No reported finding lacks a typed artifact; no model self-confirmation path across the end-to-end run (not_started)

> **Focused-test count:** TG1: 3 · TG2: 4 · TG3: 3 · TG4: 3 · TG5: 2 · TG6: 4 = **19 Tier-1** + **5 Tier-2 PBT** (2.11, 3.8, 4.8, 4.9, 4.10) = **24 dedicated**; +3 e2e (6.1–6.3) counted in TG6 above and the negative-guard (6.4) = **27 total** (within 16–34).

---

## Dependency Mapping & Critical Path

```
[Phases 1–4 landed: P1 · P2 · P3 · Phase-4 race · Phase-3 inventory]  ◀── HARD prerequisite
        │
        ▼
TG1 Model Intake ──► TG2 Catalog & Tests ──► TG3 Orchestrator ──┐
                                                                ├──► TG5 Report+Tools ──► TG6 Testing
TG4 Evidence Gate (fixtures) ───────────────────────────────────┘
   ▲ parallel with TG2/TG3
```

- **All groups** depend on the Phase-1–4 primitives being available (hard, external).
- **TG2** depends on **TG1** (tests attack a proposed model) and on Phase-3 params + Phase-4 harness.
- **TG3** depends on **TG2** (dispatches its tests) and on P1/P2/P3 + the Phase-4 harness.
- **TG4** depends only on the artifact/model *shapes* for its inputs; otherwise develops against **synthetic (model, sequence, artifact) fixtures** — no dependency on TG3 wiring.
- **TG5** depends on **TG3 + TG4** (gated result → report) and on `report/state.py`.
- **TG6** depends on **all** groups.

**Critical path:** `TG1 → TG2 → TG3 → TG5 → TG6` (model → tests → orchestrator → report → testing). The evidence gate (TG4) is off the critical path.

---

## Parallelization

- **TG4 (Evidence Gate)** develops in parallel with **TG2/TG3** against synthetic (model, executed-sequence, artifact) fixtures, then plugs in at **TG5**. With two developers this removes TG4 from the schedule and saves roughly one iteration — and front-loads the noise-control invariants (evidence-gated reporting, no-self-confirmation) that most reduce false positives for this highest-risk phase.
- **Dev A:** TG1 → TG2 → TG3 → TG5. **Dev B:** TG4 (fixtures) then joins TG5/TG6.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Model Intake | 1.5 |
| TG2 Catalog & Violation Tests | 2 |
| TG3 Execution Orchestrator | 2 |
| TG4 Evidence Gate | 1.5 (parallel) |
| TG5 Report & Tool Surface | 1 |
| TG6 Testing | 1 |
| **Total (sequential)** | **~9 iterations** |
| **With TG4 parallelized** | **~8 iterations** |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 focused tests pass.
- [ ] **Gate 3** — all Tier-2 PBT invariants validated (evidence-gated reporting, no self-confirmation, reproducibility, invariant-violation soundness, primitive-reuse fidelity).
- [ ] **Gate 4** — security audit on the pre-validated system (every reported violation carries a typed artifact; no model self-confirmation path; reproductions re-run to the same disallowed state).
