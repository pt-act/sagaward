# Phase 4 — Race Condition Harness — Tasks

> Spec-Architect PBT variant · Primitives **P1 + P2** (reused) · Feature **F4**.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.
> **Depends on Phase 1 (P1 identity store + P2 differential engine) — COMPLETE.**

> **PM amendments (v1.1, pre-kickoff):** (1) TG3 split — P2 produces the pairwise state delta; a **new commit-count aggregator** counts over N outcomes + delta magnitude (not P2, not a second differ). (2) TG6 e2e tests require a **deterministic check-then-mutate window** in the seeded target. (3) TG1 adds the **scope gate** before fan-out. (4) TG4 adds **bounded retry on inconclusive**. Focused-test count updated accordingly.

---

## Overview

Six task groups build the race harness on top of Phase 1: a **concurrency dispatcher** (N copies, shared session, jitter, scope-gated), a **precondition & reset manager** (P1-backed), an **outcome collector + state-diff integration** (P2 pairwise delta + new commit-count aggregator), a **verdict & evidence** layer (impact-gated, bounded-retry), the **agent tool surface** (F4), and **testing**. Critical path is `precondition → scope-gated dispatch → collect+diff+count → verdict → tool`. The **verdict + aggregator develop in parallel** against synthetic `(baseline, post-action, outcome)` tuples while the dispatcher is built — no live concurrency needed for their PBT, mirroring Phase 1's differ-against-fixtures approach. Total focused tests: **24** (within 16–34). Target: **~4.5 iterations**.

---

## Task Group 1 — Concurrency Dispatcher (+ scope gate)

### Implementation
- [ ] 1.1 Fan-out N identical copies of a request set over the Phase 1 replay send path (`caido_api.replay_send_raw`) under `asyncio`, joining on all N (not_started)
- [ ] 1.2 Carry a single **shared** P1 session (cookies/tokens) across all copies; no per-copy auth divergence (not_started)
- [ ] 1.3 Bounded **jitter window**: apply slight per-copy timing offsets; capped default N; rate-respecting (no unbounded loop / flooding) (not_started)
- [ ] 1.4 **Scope gate (F-11):** before any fan-out, assert the target is in scope (`scope_rules`); out-of-scope → refuse to dispatch (no concurrent requests sent), surfaced as a scoped refusal (not_started)

### Validation Tier 1: Focused Testing
- [ ] 1.5 Dispatch fans out exactly N copies, all sharing one session; joins on all N (1 test) (not_started)
- [ ] 1.6 Bounded concurrency: N is capped, no unbounded loop; jitter offsets stay within the declared window (1 test) (not_started)
- [ ] 1.7 **Scope gate: an out-of-scope target is refused with zero requests dispatched** (1 test) (not_started)

### Security Readiness Checklist
- [ ] 1.8 Shared-session credentials redacted in copy logs and tool returns (inherited from P1) (not_started)
- [ ] 1.9 No DoS-shaped flooding: dispatch respects the bounded N and rate limits (not_started)
- [ ] 1.10 No state mutation against a non-owned target — the scope gate precedes both dispatch and precondition setup (not_started)

---

## Task Group 2 — Precondition & Reset Manager (P1-backed)

### Implementation
- [ ] 2.1 Drive the target to a declared precondition state (e.g. `balance=100`, `token unused`, `coupon unredeemed`) using a P1 identity; record a captured **baseline** observable state, **read as an HTTP response** (not_started)
- [ ] 2.2 Reset to the same declared precondition between independent trials **and between bounded retries** (not_started)
- [ ] 2.3 Mark a trial **inconclusive** (never safe, never dropped) when the precondition cannot be reached (not_started)

### Validation Tier 1: Focused Testing
- [ ] 2.4 Setup reaches and records the declared precondition baseline (1 test) (not_started)
- [ ] 2.5 Reset returns to baseline between trials; trial provably starts from precondition (1 test) (not_started)
- [ ] 2.6 Unreachable precondition → inconclusive, not safe, not dropped (1 test) (not_started)

### Security Readiness Checklist
- [ ] 2.7 Precondition subject is a per-target P1 identity; no cross-target state access; precondition setup is scope-bounded (not_started)

---

## Task Group 3 — Outcome Collector + State-Diff + Commit-Count (P2-backed pairwise + new aggregator)

### Implementation
- [ ] 3.1 Collect every per-copy response (status, body, set-cookie) with no drops; parse via `parse_raw_response` into the differ's input shape (not_started)
- [ ] 3.2 Read back **post-action observable state** as an HTTP response (balance / order list / token validity); fall back to per-copy commit signals and record absence of an independent oracle (not_started)
- [ ] 3.3 **P2 pairwise delta (reused):** feed baseline + post-action state into the **reused P2 differential engine** (same volatile-field normalizer) → a concrete **state delta**. Do **not** extend P2 to count commits (not_started)
- [ ] 3.4 **Commit-count aggregator (new Phase-4 component):** a small, pure function reducing the **N per-copy outcomes + the P2 state-delta magnitude** → a **commit count**. Not a second differ; counts over P2's output + outcomes only (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.5 Outcome collection drops no copy; per-copy failures surface instead of vanishing (1 test) (not_started)
- [ ] 3.6 P2 diff yields a state delta from baseline vs. post-action on a fixture (1 test) (not_started)
- [ ] 3.7 **Commit-count aggregator: N outcomes + a multi-commit delta → count > 1; a single-commit delta → count = 1** (1 test) (not_started)

### Security Readiness Checklist
- [ ] 3.8 No second differ introduced — diffing routes through P2; the aggregator only counts; no credential material in delta or count output (not_started)
- [ ] 3.9 Missing observable oracle is recorded (glass-box), not silently treated as safe (not_started)

---

## Task Group 4 — Verdict & Evidence  *(parallel: develops against synthetic tuples)*

### Implementation
- [ ] 4.1 Verdict function, **pure over (state delta, commit count)**: count > 1 (or balance/order/token delta inconsistent with one action) → race candidate; ≤ 1 / idempotent → safe; no collision → inconclusive (not_started)
- [ ] 4.2 **Bounded retry on inconclusive (F-7):** on a no-collision result, retry from precondition up to **R** attempts (R capped default), reset between attempts, record the retry count; finalize *inconclusive* only after R (not_started)
- [ ] 4.3 Keep jitter/timing **out** of the verdict path (timing is the trigger, not the judge) (not_started)
- [ ] 4.4 Impact-gating wire-up: attach the before/after state-delta diff as evidence into `report/state.py` `vulnerability_reports`; suppress report when no multi-commit delta (not_started)

### Validation Tier 1: Focused Testing
- [ ] 4.5 Multi-commit (delta + count > 1) → race candidate; single-commit → safe (1 test) (not_started)
- [ ] 4.6 Empty / single-commit delta → no finding promoted (impact-gating) (1 test) (not_started)
- [ ] 4.7 **Inconclusive → bounded retry: a no-collision trial retries up to R from precondition, then finalizes inconclusive with the retry count recorded** (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 4.8 PBT — **single-use enforcement**: `∀ single-use precondition, N concurrent redeems: ≤ 1 commit, else flagged` (not_started)
- [ ] 4.9 PBT — **detection determinism**: `∀ runs with identical state deltas + outcomes → identical commit count → identical verdict` (not_started)
- [ ] 4.10 PBT — **no side effect on safe target**: `∀ idempotent endpoint → count ≤ 1 → reports no race` (not_started)

### Security Readiness Checklist
- [ ] 4.11 Verdict + commit count reproducible from recorded deltas/outcomes regardless of timing (not_started)
- [ ] 4.12 Report evidence contains the state diff, never cleartext shared-session creds (not_started)

---

## Task Group 5 — Agent Tool Surface (F4)

### Implementation
- [ ] 5.1 `@function_tool` race-harness action: inputs = request set + declared precondition + N + jitter (+ retry bound R); mirrors `strix/tools/proxy` conventions (`_ctx_client`, JSON returns) (not_started)
- [ ] 5.2 Return the per-copy outcome table + P2 state diff + **commit count** + verdict (race / safe / inconclusive) (not_started)
- [ ] 5.3 Surface trial controls: repeat-from-precondition retry; record N, jitter, retry count, precondition, the scope decision, and the state read used (glass-box) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 5.4 Tool returns outcome table + state diff + commit count + verdict for a seeded single-use endpoint (1 test) (not_started)
- [ ] 5.5 Glass-box: tool return records N, jitter window, retry count, precondition, scope decision, and the state read (1 test) (not_started)

### Security Readiness Checklist
- [ ] 5.6 Tool returns redact shared-session credentials in the outcome table (not_started)

---

## Task Group 6 — Testing (integration & gap-fill)

> **All e2e race tests use a seeded test target with an artificially widened, deterministic check-then-mutate window** (e.g. an explicit server-side sleep between read and commit) so collisions reproduce **every run** — these are hermetic gates, not timing-flaky. Use `tempfile`/`tmp_path` for any trial-record fixtures (Phase 3 hermeticity lesson).

### Validation Tier 1: Focused Testing
- [ ] 6.1 End-to-end **double-redemption**: precondition → N concurrent redeems against the deterministic-window target → multi-commit state delta + count > 1 → race candidate with state-diff evidence (1 test) (not_started)
- [ ] 6.2 End-to-end **safe target**: idempotent/locked endpoint (same deterministic harness, guarded) under the same N → count ≤ 1 → reported safe, no finding (1 test) (not_started)
- [ ] 6.3 **Precondition-isolation** end-to-end: two back-to-back trials each start from baseline; prior mutation does not masquerade as a race (1 test) (not_started)

### Security Readiness Checklist
- [ ] 6.4 Full PBT suite (4.8, 4.9, 4.10) green before audit gate (not_started)
- [ ] 6.5 No shared-session credential leakage across the end-to-end path (logs, outcome table, report) (not_started)
- [ ] 6.6 Scope gate exercised end-to-end: an out-of-scope target produces a scoped refusal with no requests sent (1 test) (not_started)

> **Focused-test count:** TG1: 3 · TG2: 3 · TG3: 3 · TG4: 3 · TG5: 2 · TG6: 4 = **18 Tier-1** + **3 Tier-2 PBT** (4.8, 4.9, 4.10) = **21** dedicated; +3 e2e gap-fill (6.1–6.3) already counted = **24 total** (within 16–34).

---

## Dependency Mapping & Critical Path

```
            (Phase 1: P1 store + P2 differential engine — prerequisite, COMPLETE)
                                   │
TG2 Precondition ──► TG1 Dispatch(+scope) ──► TG3 Collect+Diff+Count ──┐
                                                                       ├──► TG5 Tool Surface ──► TG6 Testing
TG4 Verdict+Aggregator (synthetic tuples) ─────────────────────────────┘
   ▲ parallel with TG1/TG3
```

- **Phase 1** is a hard prerequisite: TG2 reuses the **P1 identity store**; TG3/TG4 reuse the **P2 differential engine** (pairwise) and add the new commit-count aggregator.
- **TG2** depends on Phase 1 P1.
- **TG1** depends on TG2 (shared session + captured request) and on the Phase 1 replay send path; its scope gate (1.4) precedes all fan-out.
- **TG3** depends on **TG1** (collects its copies) and on Phase 1 **P2** (pairwise delta); the commit-count aggregator (3.4) is new and counts over P2's output.
- **TG4** depends only on the **(state-delta, outcome) shape** from TG3 for its inputs; otherwise develops against **synthetic tuples** — no dependency on live dispatch.
- **TG5** depends on **TG3 + TG4** and on `report/state.py` for impact-gating.
- **TG6** depends on **all** groups + the deterministic-window test target.

**Critical path:** `TG2 → TG1 → TG3 → TG5 → TG6`. The verdict + aggregator (TG4) are off the critical path (synthetic-tuple development).

---

## Parallelization

- **Within Phase 4:** **TG4 (Verdict + commit-count aggregator)** develops in parallel with **TG1/TG3** against synthetic `(baseline, post-action, outcome)` tuples, then plugs in at TG5 — mirroring Phase 1's differ-against-fixtures. With two developers this removes TG4 from the schedule and saves roughly one iteration. **Dev A:** TG2 → TG1 → TG3 → TG5. **Dev B:** TG4 (tuples) then joins TG5/TG6.
- Across phases: Phase 4 depends only on the completed Phase 1 P1/P2 substrate; it shares no build surface with the propose–dispose specs and can run alongside them.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Concurrency Dispatcher (+scope gate) | 1 |
| TG2 Precondition & Reset Manager | 1 |
| TG3 Outcome Collector + State Diff + Commit-Count | 1 |
| TG4 Verdict + Aggregator & Evidence | 0.75 (parallel) |
| TG5 Agent Tool Surface | 0.5 |
| TG6 Testing | 0.75 |
| **Total (sequential)** | **~4.5 iterations** |
| **With TG4 parallelized** | **~4 iterations** |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 focused tests pass (incl. scope-gate refusal, commit-count aggregator, bounded-retry, deterministic-window e2e).
- [ ] **Gate 3** — all Tier-2 PBT invariants validated (single-use enforcement, detection determinism, no-side-effect-on-safe-target; precondition isolation exercised by TG2 tests + TG6.3; scope-bounded dispatch by TG1.7 + TG6.6).
- [ ] **Gate 4** — security audit on the pre-validated system (impact-gating + P1 credential-scoping evidence attached; bounded-concurrency + bounded-retry / no-DoS confirmed; scope gate confirmed pre-dispatch).
