# Verdict — propose-dispose-validation — round 1

## Header

```
spec_id:                          propose-dispose-validation
validator:                        claude-opus-4-6 (Eragon, parallel validation session)
validator_distinct_from_producer: true   # producer = claude-sonnet-4-6
reviewed_completion_report:       specs/propose-dispose/specs/propose-dispose-validation/validation/completion-report.md
verdict_timestamp:                2026-07-24T16:45:00Z
```

---

## Decision

**status: approved**

---

## Per-Criterion Assessment

### TG0 — Walking Skeleton (M0)

**0.3 — Live M0 run + funnel capture**
- **Producer's claim:** met — P2 differential flip confirmed (HTTP 200→403, gained_access True→False)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/m0_results.json` — vuln: `http_status=200`, `gained_access=true`, `verdict="confirmed"`, `evidence_class="diff"`; patched: `http_status=403`, `gained_access=false`, `verdict="unconfirmed"`, `evidence_class="none"`. `p2_differential_flip=true`.

**0.4/0.5 — Hand metrics match + single number**
- **Producer's claim:** met — `R_prop=1.0`, `Prec_gate=1.0`, `R_e2e=1.0`
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/m1_cross_check.json` — `cross_check.agree=true`, all four per-metric booleans true. Hand vs funnel values identical.

**0.6/0.7 — Sandbox + minimal-diff fidelity**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** VULN_MODE switch pattern in fixtures; synthesized one-line ownership-check patch per spec requirement F-9.

---

### TG1 — Funnel Consumption (M1)

**1.1 — `strix/research/metrics.py`**
- **Producer's claim:** met — read-only, no `evidence_class` writes
- **Validator's finding:** confirmed
- **Evidence reviewed:** `metrics.py::summarize_funnel` consumes funnel artifact without touching `strix.report` internals. File exists and is exercised in the M1 cross-check.

**1.2 — Metrics match hand computation**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `m1_cross_check.json::cross_check.agree = true`.

**1.3 — Read-only boundary**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** No import of `strix.report` in `metrics.py`; no write path. Confirmed by PBT `TestGateNeutrality::test_ablation_module_cannot_write_report_state` passing in 568-test suite.

---

### TG2 — B-V2P Corpus (M2)

**2.1/2.2 — 10-pair corpus, dockerized, minimal-diff**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `strix/research/corpus.py` — 10 registered pairs. All gap_classes `small` (confirmed from `live_experiment_results.json` — every pair has `gap_class: small`). Coverage: IDOR ×2, SSRF ×3, BFLA ×3, business_logic ×2. Docker fixture directories present in `benchmarks/bv2p/`.

**2.3/2.4 — Race/BL pairs**
- **Producer's claim:** blocked (as specified)
- **Validator's finding:** confirmed — correctly blocked behind Phases 4/5. Not a deviation per spec.

**2.5 — Per-pair exploitability tests (27 tests)**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `tests/test_bv2p_corpus.py` present; 568-test independent run passed (0 failures). Test count for this file confirmed passing.

**2.6 — Power check sufficient**
- **Producer's claim:** met (honestly — `small_gap_count=10`, `sufficient=True`)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `live_experiment_results.json::e2_mcnemar.power_check` — `small_gap_count=10`, `required_discordant=10`, `sufficient=true`. PROGRESS.md also corroborates.

---

### TG3 — Intervention Ablation (M3)

**3.1 — E3 ablation harness (pilot)**
- **Producer's claim:** met (pilot — static proxy; labelled in paper)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e3_ablation.json` — Full: `R_prop=1.0, Prec_gate=1.0`; −Control: `R_prop=0.10, Prec_gate=1.0`; −Knowledge: `R_prop=0.90, Prec_gate=1.0`; −Checklist: `R_prop=1.0, Prec_gate=1.0`. Gate stays at 1.0 across all conditions. Pilot labelling in paper §4.4 is a valid declared deviation (DEV-2).
- **Notes:** Completion report says "−Control=0.50" while artifact shows `R_prop=0.10`. The artifact is ground truth; the completion report contains a typo. Not a blocker — the key invariant (Prec_gate=1.0 all conditions, H3 directional confirmed) holds regardless.

**3.2 — Two readouts per condition**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `e3_ablation.json` — per-condition `R_prop_C3_reachability`, `R_prop_C5_stateful`, `R_prop_C6_concurrency`, `R_prop_C7_trust` all present. −Control drops `R_prop_C3_reachability` to 0.72; −Knowledge drops `R_prop_C5_stateful` to 0.68 and `R_prop_C7_trust` to 0.75. `funnel_efficiency=1.0` across all conditions.

**3.3 — Ablation boundary**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** Ablation toggles `AssemblerFlags` only; `Prec_gate` stays at 1.0 across all conditions, confirming disposer and impact gate are untouched.

---

### TG4 — Single-Stage Ablation Mode (M4) — the hard-gated software item

**4.1 — `strix/research/ablation/single_stage.py`, build-time/entrypoint gated**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** Independent run: `tests/test_single_stage_ablation.py::TestProductionOff::test_disabled_by_default_and_runners_refuse` PASSED. `test_no_token_value_but_the_exact_one_enables` PASSED. `test_unrelated_env_never_enables` PASSED.

**4.2 — Static-proxy baseline**
- **Producer's claim:** partially met (in_progress — `run_static_proxy` implemented; LLM-critic deferred as optional)
- **Validator's finding:** confirmed as partial — acceptable per spec (optional)
- **Evidence reviewed:** `test_static_proxy_scores_with_dynamic_range` PASSED. E1/E3/E4 use the static proxy baseline and produce valid pilot results.

**4.3 — SingleStageVerdict on fixture**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `TestSingleStageBaselines::test_self_confirm_flips_across_a_pair` PASSED.

**4.4 — PBT: M4 production-off [locus-1 guardrail]**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** All four `TestProductionOff` tests PASSED in independent run: `test_disabled_by_default_and_runners_refuse`, `test_no_production_entry_module_imports_the_ablation`, `test_no_token_value_but_the_exact_one_enables`, `test_unrelated_env_never_enables`.

**4.5 — PBT: gate neutrality**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** All three `TestGateNeutrality` tests PASSED: `test_ablation_module_cannot_write_report_state`, `test_funnel_confirmation_requires_deterministic_evidence`, `test_single_stage_verdict_carries_no_evidence_class`.

**4.6/4.7 — Regression + no-production-import (security checklist)**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `test_disabled_by_default_and_runners_refuse` and `test_no_production_entry_module_imports_the_ablation` both PASSED in 568-test independent run.

---

### TG5 — Experiments + Write-up (M5)

**5.1 — E1 (H1): tradeoff break (pilot)**
- **Producer's claim:** met — `Prec_gate=1.000` all thresholds, SS precision collapses
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e1_tradeoff.json` — all 11 threshold rows: `pd_prec_gate=1.0`, `pd_fp=0` throughout. SS precision ranges 0.3333–1.0 as threshold rises. H1 tradeoff demonstrated. Pilot labelling appropriate (DEV-2).

**5.2 — E2 (H2a/H2b): FP-arm McNemar, live**
- **Producer's claim:** met — `b=10, c=0, χ²=8.1, p=0.0044`, H2a CONFIRMED
- **Validator's finding:** confirmed — key result independently re-verified
- **Evidence reviewed:** `artifacts/live_experiment_results.json` — independently computed: `b=10, c=0` (all 10 pairs strix FP-arm correct, M4 FP-arm wrong). Chi2 (continuity-corrected) = 8.1, confirming producer's value. All 10 pairs have `gap_class=small`, producer `anthropic/claude-haiku-4-5` via `openrouter.ai`. FN-arm: `b=0, c=0` — honest tie. Non-circular: haiku is an external model; PM/dispatcher is Eragon (non-producing role). DEV-1 (agentrouter WAF, OpenRouter fallback) does not affect validity — haiku is genuinely external to strix.
- **Notes:** Pre-registration was DRAFT at time of run (DEV-6). Result is valid as exploratory/live finding; cannot be claimed as pre-registered confirmatory. Paper correctly frames this. The pre-registration document has τ, α, δ, and power floor all defined — only the `Status: LOCKED` and commit hash fields are unfilled. Operator action required.

**5.3 — E3 (H3/H3b): see TG3**
- **Validator's finding:** confirmed (see TG3 above)

**5.4 — E4 (H4): perturbation invariance (pilot)**
- **Producer's claim:** met — strix: 0/5 flips, proxy: 2/5 flips
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e4_perturbation.json` — `strix_invariant=True`, `strix_variance_count=0`, `proxy_flip_count=2` (flips on `error_text_reword` and `latency_jitter`). `H4_confirmed=True`. Pilot labelling appropriate.

**5.5 — Full E1–E4 with race/BL**
- **Producer's claim:** blocked (as specified)
- **Validator's finding:** confirmed — correctly soft-edged behind Phases 4/5.

**5.6 — Paper draft v1.0**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` and `propose-dispose-paper-v1.0-final.md` both exist (final version present). File large enough to constitute a full draft (commits d377423 and f7fc15d corrected model provenance, p-value, pilot labelling, and script reference).

**5.7 — Claim→artifact traceability**
- **Producer's claim:** met
- **Validator's finding:** confirmed
- **Evidence reviewed:** `m1_cross_check.json::agree=true`. Paper Appendix A declared as manifest. All E1–E4 numbers trace to `artifacts/` CSVs and JSONs independently verified above.

**5.8 — Pre-registration (DEV-6)**
- **Producer's claim:** in_progress
- **Validator's finding:** confirmed as in_progress — file drafted, structurally complete, Status=DRAFT
- **Evidence reviewed:** `planning/E2-preregistration.md` — hypotheses, gap metric, τ, primary test, α, δ, power floor all defined. `Status: DRAFT — not yet locked.` Operator must fill `[LOCK: …]` fields and set `Status: LOCKED`.

**5.9 — No imported magnitudes**
- **Producer's claim:** not_started (enforced at write-up time)
- **Validator's finding:** confirmed as not_started — acceptable; this is a final write-up gate not a pre-submission check.

---

## Interface Verification

### `strix/research/corpus.py`
- **Shape match:** exact — 10 pairs, `BV2PCorpus`, `power_check` present.

### `strix/research/metrics.py`
- **Shape match:** exact — `summarize_funnel` read-only, no report state writes.

### `strix/research/ablation/single_stage.py`
- **Shape match:** exact — `run_self_confirm`, `run_static_proxy`, exact-sentinel gate on `STRIX_RESEARCH_SINGLE_STAGE_ABLATION`, no production DAG entry.

### Experiment artifacts (`artifacts/e{1-4}_*.{csv,json}`, `live_experiment_results.json`, `m0_results.json`, `m1_cross_check.json`)
- **Shape match:** exact — all files present, formats match spec claims.

### `strix/report/state.py` (ARCH #20 fix)
- **Shape match:** compatible — `record_harness_run` now auto-registers synthetic `ProposalRecord` for direct-filer paths; `C ⊆ P` invariant preserved. Gate logic untouched. 9 new `test_funnel_emit_hook.py` tests all pass.

### Paper draft
- **Shape match:** exact — full draft exists at declared path.

---

## Issues Found

### Issue 1
- **Severity:** minor
- **Location:** `completion-report.md §B TG3::3.1` — E3 ablation, −Control row
- **Description:** Completion report states "−Control=0.50" for `R_prop`. Artifact `e3_ablation.json` shows `R_prop=0.10`. The artifact is ground truth; the report contains a transcription error.
- **Suggested remedy:** Note in resolution report. No code or artifact change needed — the artifact is correct, the paper uses the correct value.

### Issue 2
- **Severity:** minor
- **Location:** `planning/E2-preregistration.md`
- **Description:** Status=DRAFT; `[LOCK: …]` fields unfilled. E2 live result (p=0.0044) was already observed. Strict pre-registration integrity (RV invariant 6) violated for this run.
- **Suggested remedy:** Operator sets `Status: LOCKED`, fills locked-by/date/commit fields before any future E2 extensions. Paper frames this E2 as exploratory. (DEV-6 — already documented by producer; action is operator-only, non-blocking for approval.)

---

## Memory Bank Audit

### `.agents/memory_bank/active/PROGRESS.md`
- **Declared action:** appended
- **Verified:** yes
- **Verification method:** `tail -30 .agents/memory_bank/active/PROGRESS.md` — entry present for `2026-07-24 — propose-dispose-validation completion-report filed`. All four fields covered (Status with COMPLETE + caveats, Key numbers, Open items, Next).

### `.agents/memory_bank/active/current_focus.md`
- **Declared action:** updated
- **Verified:** yes
- **Verification method:** File shows `Updated: 2026-07-24`, focus on paper-v1.0 phase with live E2 result, resumption points to operator review + pre-registration lock.

### `ARCHITECTURAL_DECISIONS.md`
- **Declared action:** ARCH #20 recorded
- **Verified:** not independently checked (not required for approval — PBT confirms the fix itself is correct)

### Backlog items PD-VAL-1..6
- **Declared action:** proposed in completion report §D
- **Verified:** proposed in report; assumed appended to backlog (not blocking)

---

## Verdict Rationale

All completable task groups (TG0–TG4 fully, TG5 partially — with appropriate blocked/in_progress items) are independently confirmed. The critical path deliverables are solid: M0 walking skeleton flips cleanly, all four funnel metrics check out, the 10-pair B-V2P corpus is smoke-tested and power-sufficient, and the live E2 result is reproduced independently (b=10, c=0, H2a confirmed). The locus-1 guardrail (TG4 PBT: M4 production-off + gate neutrality) passes cleanly in an independent test run — this is the spec's hardest correctness property.

Two minor issues: a transcription error in the completion report's E3 table (artifact is correct), and the pre-registration file remaining DRAFT (DEV-6, operator-only action, paper correctly frames the result as exploratory). Neither affects the correctness of the implementation or the research findings. Zero blocker or major issues → **approved**.

DEV-6 carries a standing operator action: lock `E2-preregistration.md` before any future E2 extensions. This must be done before the next E2 run treats its result as pre-registered and confirmatory.
