# Resolution Report — phase-5-business-logic-testing

## Header
spec_id: phase-5-business-logic-testing
type: integration
final_status: approved
cycle_started: 2026-06-16 (manifest `phase_started`)
cycle_closed: 2026-06-17 (§E integration verdict)
rounds: 3 producer–validator rounds
arbiter_invoked: false

## Participants
- producer: `kimi-k2p7-code` (Kimi K2 / Moonshot, served via Fireworks, run under a claude-code-derived harness; recorded in the manifest as `claude-kimi-k2p7-code` — the `claude-` prefix is the harness, not the model)
- validator: `opus-4.8-pm-auditor` (Anthropic Opus 4.8) — distinct vendor and model from the producer
- arbiter: n/a (no contested disagreement occurred)

## Outcome Summary
Delivered the Phase-5 business-logic state-testing capability: agent-proposed journey/state-model intake with a per-engagement store, a fixed five-kind invariant catalog (step-skip, replay, double-spend, price-mismatch, unauthorized-state-change), an execution orchestrator wiring the P1/P2/P3/P4 primitives, the evidence gate (promote iff typed artifact ∧ model-impossible state ∧ reproducibility), a four-affordance agent tool surface (intake submit/read, list-invariants-for-flow, run-violation, read-gated-result), and a seeded vuln/patch benchmark fixture. Two defects found and resolved across the cycle: the evidence gate's reproducibility pillar was unwired in the production path (round 1), and double-spend/price-mismatch shipped as non-functional stubs with the P1–P4 composition unexercised (integration audit). At close, all five invariant kinds are functional, the gate is non-inverted in both directions (verified by a validator-constructed negative battery against the real orchestrator), and the full gate is green (315 passed, 4 skipped, 19 subtests). No operator escalations are open. One non-blocking item remains: the live Docker e2e tests are written but skip without a daemon — a one-time live-fire run in a Docker-available environment is recommended.

## Artifact Index
- Final completion report: `specs/phase-5-business-logic-testing/validation/completion-report.md`
- Final verdict: `specs/phase-5-business-logic-testing/validation/verdict.md` (§E integration, `approved`, on `2a47d9e`)
- Verdict history:
  - `verdict-history/verdict-01.md` — round 1 (`db008f0`), `needs_revision` (reproducibility blocker, TG5 surface, minor PBT/e2e/pytest gaps)
  - `verdict-history/verdict-02.md` — round 2 (`4ee31f4`), unit-contract `approved`, then integration-scope correction to `needs_revision` (type:integration → §E; double-spend/price-mismatch stubs)
- Arbiter audit: n/a
- Implementation artifacts (branch `phase-5-business-logic-testing` @ `2a47d9e`, squash-merged to `main`):
  - `strix/core/logic/{models,store,catalog,context,orchestrator,gate}.py`
  - `strix/core/paths.py` (`logic_model_path`)
  - `strix/tools/logic/{__init__,tools}.py`; registration in `strix/agents/factory.py::_BASE_TOOLS`
  - `benchmarks/business_logic_fixture/{app.py,Dockerfile,README.md}` (vuln/patch target; doubles as the first B-V2P pair)
  - `tests/{test_logic_model,test_logic_catalog,test_logic_orchestrator,test_logic_gate,test_logic_pbt,test_logic_tools,test_logic_integration}.py`
  - `tests/integration/test_business_logic_fixture.py` (Docker e2e, daemon-gated)
  - `pyproject.toml` (+ `uv.lock`): `pytest` / `pytest-asyncio` pinned, `[tool.pytest.ini_options]`

## Interfaces Delivered (manifest `produces`)
- `business_logic_orchestrator` — `function{flow, invariant_kind} → executed sequence + deterministic artifact`. Delivered: `BusinessLogicOrchestrator.run`.
- `violation_report` — `vulnerability_report{violated_invariant, executed_sequence, artifact: diff|callback|race_result}`. Delivered via `run_business_logic_violation_test` → `report/state.py` impact gate; `evidence_class` reuses the existing allowlist (no new class).

## Lessons for Future Specs
1. **Branch the validation method on spec `type` from round 1.** This spec is `type: integration`, but the first two rounds were validated at unit level; the §E composition obligation surfaced only at the integration audit. Encode: the validator reads the manifest `type` *before* choosing its method — integration specs require the composition to be exercised in the very first verdict, and a verdict that cites only unit/mock artifacts is malformed (§E).
2. **Precision-owning components need a test at the *production caller*, not just the unit.** The reproducibility blocker hid because tests drove `evaluate` directly with an explicit reproduce fn; nothing exercised `orchestrator.run`. Require a true-negative test on the production path for any flag/detect/confirm/dispose component (v2.1).
3. **Every precision-owning detector needs a true-positive that actually fires.** double-spend/price-mismatch shipped returning `reached_impossible=False` unconditionally; the suite was green because only true-negatives (which a permanently-silent stub trivially passes) were exercised. A green suite does not prove a detector can fire — pair every TN with a TP that confirms.
4. **"Done" means pushed-and-verified, never in-working-tree.** A tool-iteration-cap-forced summary (harness `agent.max_turns`) once reported unpushed local work as "on origin." Mitigation (now standing practice): push per task-group and confirm `git diff --stat origin/<branch>` is empty before any completion claim; size the iteration cap so a forced summary cannot catch unpushed work.
5. **Build the seeded fixture once and reuse it.** The vuln/patch `business_logic_fixture` serves as both the §E integration test bed and the first business-logic B-V2P corpus pair for `propose-dispose-validation` (M2). Downstream specs should consume it, not rebuild it.
6. **Toolchain reliability is a validation dependency (for `emergent_failures.md`).** A mis-set compaction-summarizer model (a stale id → 404) silently degraded the producer mid-task by inserting a fallback marker instead of aborting. Defenses now in place: a corrected summarizer model, `compression.abort_on_summary_failure`, a context re-sync hook (6 triggers), and push-per-task-group. Future long-running specs should assume mid-iteration context loss and rely on on-disk continuity, not chat memory.

---
*Cycle closed `approved`. The manifest `history` references this report; downstream specs (notably `propose-dispose-validation`) consume it rather than the full validation directory.*
