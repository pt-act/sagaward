# Phase 5 Kickoff — Locked Contracts + Coder Prompt

> Business-Logic State Testing (feature F5). **Terminal phase — the capstone, and the propose–dispose doctrine stated in code.** Consumes every earlier primitive.
> Source of truth: `.agents/specs/phase-5-business-logic-testing/{spec.md,tasks.md}` + `manifest.yml`.
> Purpose: lock the model-intake / catalog / orchestrator / **evidence-gate** contracts before coding, and lock the validation discipline this highest-noise phase demands.

## Preconditions (verified)
- Phases 0–4 merged to `main` (`ca4fd09 Phase 4 race harness v2 (#7)`). The full disposer substrate is live and **corrected**: P1 identity/replay + P2 differential (BFLA/expired direction fixed), P2 OOB oracle (record_hit/timestamp/DNS-token fixed), P3 inventory + reachability + param classes, Phase-4 race harness (aggregator magnitude/unit fixed).
- Consumes: `identity_store` + `replay_engine` (P1), `differential_engine` (P2 diff), `inject_confirm_tool`/OOB (P3 callback), `race_harness_tool` (Phase-4), `ranked_surface_map` + `parameter_classifier` (Phase-3), `impact_gate` (`report/state.py`).
- **Branch from `main`** (it has P0–P4): `git checkout -b phase-5-business-logic-testing main`.

---

## DECISIONS / locked notes (read before coding)

1. **Reuse the *corrected* primitives — never re-implement.** Double-spend → the Phase-4 race harness; replay/identity → P1; diff → P2; callback → P3; surface/params → Phase-3. Phase 5 adds **only** intake, catalog, orchestrator, gate, report/tools. (Invariant #6 primitive-reuse-fidelity is PBT'd.)
2. **Race-harness integration carries the commit unit.** When the double-spend test invokes the Phase-4 harness, it **must pass the modeled `state_counter` + `commit_unit`** (from the journey model's monetary-operation relation) into the harness `Precondition`. The aggregator now divides magnitude by the declared per-commit unit and **fails safe to 1 (= safe) when the unit is unknown** — so a double-spend test that omits the unit will *silently miss the race*. The model's monetary relation is the source of that unit.
3. **Evidence vocabulary is composed, not extended.** Phase 5 adds **no new `evidence_class`** value — a confirmed violation reuses `diff` ∨ `callback` ∨ `race_result`. The `vulnerability_report` carries the **violated invariant + executed sequence (reproduction) + the backing artifact**. Do not invent a `business_logic` evidence class.
4. **This phase is the doctrine in code — the evidence gate is the whole point.** The agent proposes the journey/state model; deterministic harnesses dispose. The proposing model is **structurally barred from the confirmation path**. This is the highest-noise bounty class; the gate is what keeps it from flooding the operator.

---

## Contract A — Journey/State-Model Intake (agent-proposed) · `strix/core/biz/` (new), durable per-engagement
- Schema (recorded, every field tagged **`agent-proposed`**): journeys (ordered steps), object lifecycles (states + allowed transitions), trust boundaries (identity ↔ step), monetary operations (amount/price/quantity relations **+ per-commit unit**), named flows (approval/coupon/refund/credit/invite).
- Endpoints/params are **referenced from the Phase-3 inventory** (classes `amount`/`state`/`role`), never re-derived.
- Durable per-engagement (mirror `strix/core/sessions.py` SQLite; path via `core/paths.py`); per-engagement scoped, no cross-target read path.

## Contract B — Invariant Catalog & Violation Tests (fixed, deterministic) · `strix/core/biz/`
- **Fixed enumerable catalog** of violation *kinds*: `step-skip`, `replay`, `double-spend/race`, `quantity/price-mismatch`, `unauthorized-state-change`. The agent selects *which kind* applies; the test logic for a kind is **identical every run** (no model output in test logic).
- Each test *executes* a sequence and produces a typed candidate artifact: step-skip/price-mismatch/unauthorized-transition → P2 diff; replay/double-spend → P2 diff ∨ Phase-4 race-result; async transition → P3 callback.

## Contract C — Execution Orchestrator (wires P1/P2/P3/P4) · `strix/core/biz/`
- One entry per invariant kind: `(flow, invariant_kind)` → the right violation test → the right primitive (P1 replay / P2 diff / P3 mint-await / Phase-4 harness).
- **Records the full executed sequence + resulting state** for reproduction.
- Emits **only typed artifacts** (diff/callback/race-result), never the model's rationale.

## Contract D — Evidence Gate (the hard control) · `strix/core/biz/` *(parallel: build against synthetic fixtures)*
- Promote a violation **iff**: (a) a deterministic artifact is attached (`diff` ∨ `callback` ∨ `race_result`), **and** (b) the executed sequence reached a state the model declared **impossible**, **and** (c) it **reproduces** (re-run → same disallowed state).
- **Rejects free-text/narrative rationale as evidence.** The proposing model is excluded from the confirmation path — there must be **no code path** where a proposal self-promotes without a typed artifact.

## Contract E — Report Integration + F5 Tools · `strix/tools/biz/`
- Confirmed violation → `add_vulnerability_report` carrying violated invariant + executed sequence + backing artifact. Unconfirmed hypotheses **never** reach `vulnerability_reports`; surfaced as explicit unconfirmed results.
- `@function_tool`s: model intake (submit/read), list-invariants-for-flow, run-violation, read-gated-result — mirror `strix/tools/proxy` (`_ctx_client`, JSON returns).
- **WIRE THE TOOLS into `_BASE_TOOLS` in `strix/agents/factory.py` + add a registration test.** (Phase-3 lesson: tools were defined but unwired — caught at close-out. Do not repeat.)

---

## Validation discipline (NON-NEGOTIABLE — this is the highest-precision-risk phase)
The evidence gate and no-self-confirmation are precision-owning logic. Per the validation upgrade, **tests must assert the security semantics, including the negative direction** — a passing test that encodes the implementation's assumption is not evidence. Mandatory negative cases (these are the ones that catch a leaky gate):
- **No-artifact candidate** (narrative only) → **not reported** (TG4.6).
- **Model-allowed state** reached → **not confirmed** (TG4.7) — the "is the state actually impossible?" guard, the analog of "is this actually a violation."
- **Non-reproducible one-off** (artifact once, not on re-run) → **not confirmed** (TG4.4/4.10).
- **Plausible-but-wrong invariant**, no artifact produced → **nothing reported** (TG6.4 — the confirmation-bias guard; this is the single most important e2e test in the phase).
The PBTs (evidence-gated reporting, no-self-confirmation, reproducibility, invariant-violation soundness, primitive-reuse fidelity) run against **synthetic (model, executed-sequence, artifact) fixtures** — no live agent.

---

## Build order (from tasks.md)
Critical path `TG1 model intake → TG2 catalog & tests → TG3 orchestrator → TG5 report+tools → TG6 testing`; **TG4 evidence gate develops in parallel against synthetic (model, sequence, artifact) fixtures** then plugs in at TG5 — front-loading the noise-control invariants. ~8–9 iterations. Gate per push: Tier-1 + the **5 PBT invariants** (invariant-violation soundness, primitive-reuse fidelity, evidence-gated reporting, no-self-confirmation, reproducibility) + ruff + `mypy --strict` (changed) + `pyright` + `bandit -r strix/ -c pyproject.toml` + full `pytest tests/`.

## Testing — deterministic, offline, hermetic
The evidence gate, catalog, and orchestrator dispatch are pure → fixture/PBT them against synthetic tuples. E2E violation tests use **deterministic in-process / patched primitives** (no live socket — patch `replay_as_identity` and the harness boundary as Phase 4 did), so the suite is hermetic. Use `tempfile`/`tmp_path` for the model/violation store, never hardcoded `/tmp`.

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Phase 5 — Business-Logic State Testing, per .agents/specs/phase-5-business-logic-testing/
{spec.md,tasks.md} and the locked contracts in this kickoff. This is the TERMINAL phase — the
propose–dispose doctrine stated in code.

START ON A FRESH BRANCH: git checkout -b phase-5-business-logic-testing main  (main has P0–P4; do
NOT stack on another branch).

LOCKED DECISIONS:
1. REUSE the corrected primitives, never re-implement: double-spend -> Phase-4 race harness;
   replay/identity -> P1; diff -> P2; callback -> P3; surface/params -> Phase-3. Phase 5 adds only
   intake, catalog, orchestrator, gate, report/tools.
2. When invoking the Phase-4 race harness for double-spend, PASS the modeled state_counter +
   commit_unit through the harness Precondition — the aggregator fails safe to 1 (=safe) when the
   unit is unknown, so omitting it silently misses the race. The model's monetary relation is the
   source of the unit.
3. NO new evidence_class — a confirmed violation reuses diff | callback | race_result. The
   vulnerability_report carries violated invariant + executed sequence (reproduction) + artifact.
4. The proposing model is STRUCTURALLY barred from the confirmation path. No code path may let a
   proposal self-promote without a typed harness artifact.

Build in critical-path order: TG1 model intake -> TG2 catalog & violation tests -> TG3 orchestrator
-> TG5 report+tools -> TG6 testing; develop TG4 evidence gate in parallel against synthetic
(model, executed-sequence, artifact) fixtures.

Honor the LOCKED interfaces exactly:
- Model intake: every field tagged agent-proposed; params referenced from Phase-3 inventory; durable
  per-engagement, scoped, no cross-target read.
- Invariant catalog: fixed/enumerable; test logic identical every run; no model output in test logic.
- Orchestrator: one entry per kind; wires P1/P2/P3/P4; records the full executed sequence; emits only
  typed artifacts.
- Evidence gate: promote iff (typed artifact) AND (reached model-impossible state) AND (reproduces).
  Rejects narrative rationale. The model never confirms itself.
- Report/tools: confirmed -> add_vulnerability_report with reproduction + artifact; unconfirmed never
  reaches vulnerability_reports. WIRE the F5 tools into _BASE_TOOLS + add a registration test.

VALIDATION DISCIPLINE (this is the highest-precision-risk phase — tests assert SECURITY SEMANTICS,
not the implementation's behavior):
- Negative cases are MANDATORY and are how a leaky gate is caught: no-artifact -> not reported;
  model-ALLOWED state -> not confirmed; non-reproducible one-off -> not confirmed; plausible-but-wrong
  invariant with no artifact -> NOTHING reported (TG6.4, the most important e2e test).
- PBTs (evidence-gated reporting, no-self-confirmation, reproducibility, invariant-violation soundness,
  primitive-reuse fidelity) run on synthetic fixtures.

CARRY-FORWARD GUARDRAILS (lessons from Phases 2/3/4 — do not repeat):
- WIRE THE TOOLS into _BASE_TOOLS + registration test (Phase-3 unwired-tools gap).
- FULL SUITE gate: pytest tests/ (not per-file) + ruff + mypy --strict (changed) + pyright +
  bandit -r strix/ -c pyproject.toml, all green together.
- HERMETIC tests: synthetic fixtures for gate/catalog PBTs; patch replay_as_identity + harness
  boundary for E2E (no live socket); tempfile/tmp_path, never hardcoded /tmp.
- A test that passes by encoding the implementation's assumption is NOT evidence — assert the
  security meaning (the BFLA and race-aggregator bugs both shipped green this way).
- CLEAN working tree: explicit git add, never -A. Memory/manifest are LOCAL-ONLY: never git-add
  .agents/ or manifest.yml. Push per task group.
- Update PROGRESS.md / current_focus.md concurrently; set manifest phase-5 status as you progress.
- At close-out the branch will be SQUASH-merged to main — keep it tidy.
```
