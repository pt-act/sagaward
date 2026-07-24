# Phase 5 Integration Closure + Propose–Dispose Onboarding — Kickoff

> **Two things this session: (1) reconcile `manifest.yml` to reality and to the propose–dispose program, then (2) close Phase 5 as a true *integration* spec.** Phase 5 is typed `integration` → VALIDATION_PROTOCOL §E governs it; a verdict on mock-context unit tests is malformed for an integration spec. Two of its five invariant kinds are non-functional stubs. This session makes the manifest honest and makes the composition real.
> Source of truth: `manifest.yml`, `.agents/specs/phase-5-business-logic-testing/{spec.md,tasks.md}`, `.agents/specs/propose-dispose/propose-dispose-manifest-integration.md`, and the validator audit `phase5-integration-audit-and-sequencing.md`.

## Purpose — why this matters (read first)
This work is the keystone of the engine's doctrine — **the agent proposes, deterministic harnesses dispose** — and it is also the substrate of a scientific result we intend to publish. The propose–dispose paper (the consolidated living preprint; **read it for the full thesis, not the superseded archive drafts in `paper/`**) sets out to test whether a structured propose-then-harness-confirm loop raises *meaningful* recall over a model confirming its own hunches. Phase 5's evidence gate, exercised across the real P1–P4 composition, is that thesis stated in code. Build it well and you are not just closing a phase — you are producing the engine whose behavior the paper measures.

**What "excellence" means here:** the discipline *is* the deliverable. You are the proposer; the harness is the judge — and the paper's whole point is that the judge must be incorruptible. So a clean **true-negative on the patch commit (gate stays silent)** is exactly as valuable as the true-positive on the vuln commit. An unflattering, honest result is a finding, never something to massage toward a confirmation. The one failure mode that would discredit both the engine and the paper is a gate that confirms what isn't there. Aim your craft at rigor, not at producing green findings.

## Preconditions (verified by the validator @ `4ee31f4`)
- Unit-contract layer of Phase 5 is **confirmed**: evidence gate precision (both directions), reproducibility wiring, no-self-confirmation, 4-affordance tool surface, full gate green (306 passed + 19 subtests). These are done — do **not** redo them.
- **Open at integration level:** `_test_double_spend` (`strix/core/logic/catalog.py:207-221`) never calls `ctx.race_harness`; `_test_price_mismatch` (`:190-204`) has no tamper logic. Both return `reached_impossible_state=False` always → can never confirm. The real P1–P4 composition has never run against a live target.
- Branch: continue on `phase-5-business-logic-testing` (currently `4ee31f4`); do **not** branch anew.

---

## STEP 0 — MANIFEST EDITS (do this FIRST, before any code)

`manifest.yml` is local-only/gitignored — **never `git add` it**. Edits are append-only in `history`; keep `history` timestamp-monotonic (the current block has an out-of-order tail — append new entries at the correct chronological position, do not rewrite past ones).

**0.1 — Correct the Phase-5 entry.** It must reflect that unit validation passed but integration closure is pending. Do NOT set `approved`.
```yaml
- id: phase-5-business-logic-testing
  ...
  status: in_review            # was in_progress; NOT approved — integration §E closure pending
  execution:                   # NEW — role distinctness is a correctness property (§B/§D)
    producer: claude-kimi-k2p7-code
    validator: opus-4.8-pm-auditor      # distinct lineage from producer
    arbiter: null
```

**0.2 — Append the validation history** (chronological, append-only):
```yaml
- timestamp: 2026-06-16T15:00:00+00:00
  event: spec_produced
  ref: phase-5-business-logic-testing
  by: claude-kimi-k2p7-code
  note: "Round 1 @ db008f0: TG1–TG6 + reproducibility blocker fix."
- timestamp: 2026-06-16T16:00:00+00:00
  event: spec_loopback
  ref: phase-5-business-logic-testing
  by: opus-4.8-pm-auditor
  note: "Verdict r1 needs_revision: TG5 tool surface incomplete (2/4 affordances); minor PBT/e2e/pytest gaps."
- timestamp: 2026-06-16T17:30:00+00:00
  event: spec_produced
  ref: phase-5-business-logic-testing
  by: claude-kimi-k2p7-code
  note: "Round 2 @ 4ee31f4: all 4 verdict items addressed; 306 passed."
- timestamp: 2026-06-16T18:30:00+00:00
  event: spec_loopback
  ref: phase-5-business-logic-testing
  by: opus-4.8-pm-auditor
  note: "Integration audit: unit contracts approved; §E closure required — double-spend/price-mismatch are stubs, composition unexercised. Stays in_review."
```

**0.3 — Add the two propose–dispose specs** (from `propose-dispose-manifest-integration.md`, with the `file:` paths CORRECTED to the real location `propose-dispose/specs/...`):
- `propose-dispose-instrumentation` (`type: unit`, `status: planned`, `depends_on: [phase-0-foundation-hardening, phase-3-attack-surface-inventory]`, `file: .agents/specs/propose-dispose/specs/propose-dispose-instrumentation/spec.md`) — produces `funnel_log`, `proposal_context_assembler`.
- `propose-dispose-validation` (`type: research`, `status: planned`, `depends_on: [phase-0, phase-1, phase-2, phase-3]`, `file: .agents/specs/propose-dispose/specs/propose-dispose-validation/spec.md`) — produces `bv2p_corpus`, `single_stage_ablation_mode`, `experiment_results`; consumes P4 `race_harness_tool` + P5 `business_logic_orchestrator` as **soft edges** (note them as gating only the race/business-logic experiments, not the whole spec).

**0.4 — Add the non-gating milestone** (after the product milestones):
```yaml
- name: propose-dispose-validated
  specs: [propose-dispose-instrumentation, propose-dispose-validation]
  status: not_started
  gating: parallel        # NON-gating to product milestones — measurement track
  note: "Startable now (P0–P3 complete); race/BL experiments light up as P4/P5 land. Must never block product milestones."
```

**0.5 — Append a `spec_added` history event** for the two new specs, and leave milestone `business-logic-ready: not_started` (it completes only when Phase 5 reaches `approved`).

**Manifest invariants to re-check after editing (PROJECT_MANIFEST §C):** unique ids, acyclic deps, interface closure (every `consumes` has a matching `produces`), integration coverage (Phase 5 ≥2 unit deps ✓), status consistency, history monotonicity.

---

## DECISIONS / locked notes (Phase-5 closure — read before coding)

1. **Reuse the corrected primitives — never re-implement.** `double-spend` → the Phase-4 race harness; `price-mismatch` → P2 diff over a tampered replay; identity/replay → P1. Phase 5 still adds **only** intake/catalog/orchestrator/gate/report/tools.
2. **Double-spend MUST carry the commit unit.** When `_test_double_spend` invokes `ctx.race_harness`, pass the modeled `state_counter` + `commit_unit` (from the journey model's monetary-operation relation) into the harness `Precondition`. The Phase-4 aggregator **fails safe to 1 (= safe) when the unit is unknown** — omit it and the test *silently misses the race*. Set `artifact_type="race_result"` and `reached_impossible_state` from the harness verdict.
3. **No new `evidence_class`.** Confirmed double-spend reuses `race_result`; price-mismatch reuses `diff`. The artifact-type allowlist `{diff, callback, race_result}` is unchanged.
4. **The gate is untouched.** `gate.py` and the reproducibility wiring are validated — do not modify them. This work fills the catalog stubs and exercises the composition; it does not touch the gate.
5. **Integration ≠ unit.** Per §E, the closing evidence is the **composition exercised against a real seeded target**, not more mock-context tests. The validator (me) will re-run the composed path; build it to be re-runnable.

---

## Contract F — `double-spend` (fill the stub) · `strix/core/logic/catalog.py`
- Build a `Precondition` from the flow's monetary operation: `state_counter` + `commit_unit`. Call `ctx.race_harness(request_id, precondition, role, n, jitter_ms)`.
- Map the `RaceResult` verdict → `reached_impossible_state` (true when the harness confirms an over-redemption) and attach the race-result artifact (`artifact_type="race_result"`).

## Contract G — `price-mismatch` (fill the stub) · `strix/core/logic/catalog.py`
- Tamper the modeled amount/price/quantity param (from the monetary operation), replay as the buyer via `ctx.replay`, capture the charged total, diff against the expected total via `ctx.diff`.
- On mismatch → `reached_impossible_state=True`, `artifact_type="diff"`; otherwise the candidate stays unconfirmed.

## Contract H — Seeded integration fixture (= the §E test bed AND Spec B's first B-V2P pair) · `benchmarks/` or `tests/integration/`
- A minimal dockerized target with (a) a single-use resource redeemable concurrently (double-spend) and (b) a step-skippable checkout. Provide **both** commits: `vuln` (violation reproduces) and `patch` (correctly gated).
- Drive the real `RealExecutionContext` (live identity store + `replay_as_identity` + the Phase-4 harness) against it.
- **This fixture is built once and reused** as the first business-logic entry of Spec B's `bv2p_corpus` (M2). Do not build a throwaway.

---

## Validation discipline (NON-NEGOTIABLE — integration §E + Amendment 1 both directions)
- **TP (sensitivity):** on the `vuln` commit, the composed path emits a confirmed, reproducible `violation_report` for double-spend (race_result) and price-mismatch (diff).
- **TN (precision):** on the `patch` commit, the gate stays silent — **no report**. This is the integration-level false-positive guard; it is mandatory, not optional.
- Keep the existing unit PBTs/negative tests green. Add the integration TP/TN as a hermetic-where-possible harness (patch the live socket boundary as Phase 4 did; the dockerized fixture is the exception used for the §E exercise).
- A test that passes by encoding the implementation's assumption is not evidence — assert the security meaning (the BFLA and race-aggregator bugs both shipped green that way).

---

## Parallel track (separate dispatch, startable now)
`propose-dispose-instrumentation` (Spec A, `unit`) has all deps complete (P0, P3) and **no Phase-5 dependency** — it can start in parallel. It builds the funnel/`ProposalRecord` telemetry you'll want in place to measure this very composition. Spec B (`research`) waits until Phase-5 closure lands (its business-logic experiments consume `business_logic_orchestrator`).

---

## Build order & gate
Manifest edits (Step 0) → Contract F (double-spend) → Contract G (price-mismatch) → Contract H (seeded fixture + §E composition run) → integration TP/TN tests → completion report. ~3–4 iterations.
Gate per push: Tier-1 + the 5 PBT invariants + the new integration TP/TN + ruff + `ruff format --check` + `mypy --strict` (changed) + `pyright` + `bandit -r strix/ -c pyproject.toml` + full `pytest tests/`, all green together. **Push per task group; then `git fetch && git diff --stat origin/phase-5-business-logic-testing` must be empty before writing the completion report.**

---

## Coder kickoff prompt (relay to Hermes)

```text
Close Phase 5 as a TRUE INTEGRATION spec (it is type: integration in manifest.yml → VALIDATION_PROTOCOL
§E: the composition must be exercised, not just unit-tested with mocks). Continue on branch
phase-5-business-logic-testing (currently 4ee31f4). Do NOT touch gate.py or the reproducibility wiring —
they are validated.

STEP 0 — EDIT manifest.yml FIRST (local-only, never git add it):
- Phase 5: status -> in_review (NOT approved); add execution: {producer: claude-kimi-k2p7-code,
  validator: opus-4.8-pm-auditor, arbiter: null}.
- Append (append-only, keep history timestamp-monotonic) the round-1 spec_produced/spec_loopback,
  round-2 spec_produced, and the integration-audit spec_loopback events.
- Add the two propose-dispose spec entries from propose-dispose-manifest-integration.md, with file:
  paths corrected to .agents/specs/propose-dispose/specs/...; add the non-gating
  propose-dispose-validated milestone; append a spec_added event.
- Re-check PROJECT_MANIFEST §C invariants (ids, acyclic, interface closure, status consistency, history
  monotonicity).

THEN THE CODE (catalog.py stubs + composition):
1. double-spend (_test_double_spend): call ctx.race_harness with a Precondition carrying the modeled
   state_counter + commit_unit (aggregator fails safe to 1 when unit unknown — omitting it silently
   misses the race). Map RaceResult verdict -> reached_impossible_state; artifact_type="race_result".
2. price-mismatch (_test_price_mismatch): tamper the modeled amount/price/quantity, replay as buyer,
   diff charged vs expected total; on mismatch reached_impossible_state=True, artifact_type="diff".
3. Seeded fixture (build ONCE, reuse as Spec B's first B-V2P pair): a dockerized target with a
   concurrently-redeemable single-use resource and a step-skippable checkout, at TWO commits — vuln and
   patch. Drive the real RealExecutionContext (live identity store + replay_as_identity + Phase-4
   harness) against it.

VALIDATION (both directions, mandatory):
- vuln commit -> confirmed, reproducible violation_report (double-spend race_result; price-mismatch diff).
- patch commit -> gate stays SILENT, no report (integration-level false-positive guard).
- Keep all unit PBTs/negative tests green. Assert SECURITY semantics, not the implementation's behavior.

GATE per push: ruff + ruff format --check + mypy --strict (changed) + pyright + bandit -r strix/ -c
pyproject.toml + full pytest tests/. Push per task group; verify git diff --stat origin/<branch> is
empty before writing the completion report. Update PROGRESS.md / current_focus.md concurrently; keep
the working tree clean (explicit git add, never -A; never git-add .agents/ or manifest.yml).

When the composed vuln/patch run lands, signal completion via the completion report — the validator
re-runs the composition under §E before Phase 5 can flip to approved.
```
