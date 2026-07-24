# Propose–Dispose Validation — Tasks

> Spec-Architect PBT variant · Feature **F-PD-B** · `type: research` · **non-gating to product milestones**.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.
> Canonical `spec.md` = `propose-dispose-validation/spec.md`; research narrative companion = `propose-dispose-research-proposal-v0.4.md`.
> **Measurement track:** most groups are research deliverables, not PBT'd software. Only **TG4** (the single-stage ablation mode) adds shippable software and carries hard Tier-2 PBT (the locus-1 guardrail). **Depends on P0–P3 + the instrumentation unit — all COMPLETE → startable now.**

---

## Overview

Six task groups map the proposal's milestones M0–M5: the **walking skeleton** (M0), **funnel consumption** (M1, reads the instrumentation unit), the **B-V2P corpus** (M2), the **intervention ablation** (M3, runs the assembler's ablation), the **single-stage ablation mode** (M4, research-only, guarded), and **experiments + write-up** (M5). Critical path is `TG0 → TG2 → TG5` on IDOR/SSRF; race/business-logic light up behind Phases 4/5 (soft edges). The disposer is never touched. Dedicated checks: **~9** (Tier-1 validations) + **2 Tier-2 PBT** (the M4 guardrail) — lean by design, as a measurement track. Target: **~8.5 iterations** (core; race/BL deferred).

---

## Task Group 0 — Walking Skeleton (M0)  *(corpus built; live run pending on operator host)*

### Implementation
- [x] 0.1 Pinned the **discriminating seed** open-webui IDOR (CVE-2024-7041) as a synthesized one-line ownership-check pair (`benchmarks/bv2p/idor_memories`, `VULN_MODE` switch) (completed)
- [x] 0.2 Containerized vuln/patch (single image + `VULN_MODE` switch, mirroring the Phase-5 fixture); live sandbox deploy is the operator-host step (completed — build; live deploy pending)
- [ ] 0.3 Run current strix against each; hand-capture the funnel — **live run on operator host** (not_started)

### Validation Tier 1: Focused Testing
- [ ] 0.4 Compute by hand: `R_prop`, `Prec_gate`, verdict-flip, surface-gap — **needs the live run** (not_started)
- [~] 0.5 **The single number** (did the P2 differential flip vuln→fixed?): demonstrated in `tests/test_bv2p_corpus.py` (the engine flags `gained_access` across the pair); the live-run datapoint with the agent's raw proposal is the operator-host step (in_progress)

### Security Readiness Checklist
- [x] 0.6 Both deployments run sandboxed; no third-party egress (fixture design + README) (completed)
- [x] 0.7 The synthesized patch changes *only* the security check (the one-line ownership gate) — minimal-diff fidelity reviewed and recorded in `core.update_memory` (completed)

---

## Task Group 1 — Funnel Consumption (M1)
> The funnel itself is built + PBT'd in `propose-dispose-instrumentation` (TG1). This group only **consumes** it — no Tier-2 PBT here.

### Implementation
- [x] 1.1 Read the four metrics off the funnel log: `strix/research/metrics.py::summarize_funnel` (reuses the `report.proposals` pure `compute_*` fns) + read-only `__main__` CLI over a `funnel.json` (completed)

### Validation Tier 1: Focused Testing
- [x] 1.2 Funnel-derived metrics match the hand-computation: `tests/test_funnel_metrics.py` (synthetic funnel + `cross_check`); wire to the live M0 numbers (0.4) on the operator run (completed — mechanism; live M0 cross-check pending the run)

### Security Readiness Checklist
- [x] 1.3 Metrics are read-only over the funnel; the harness writes no report state and sets no `evidence_class` (completed)

---

## Task Group 2 — B-V2P Corpus (M2)

### Implementation
- [x] 2.1 Build the **small-gap-biased** corpus: IDOR (P1/P2) + SSRF (P3) M0 seeds in `strix/research/corpus.py` + `benchmarks/bv2p/{idor_memories,ssrf_fetch}` (BFLA/blind-XXE added as the corpus grows) (completed)
- [x] 2.2 Each pair ships ground-truth `V` (`vuln_endpoint`), is dockerized, and is minimal-diff (IDOR synthesized one-line ownership check; SSRF the 3.0.13 internal-block fix reusing P0) (completed)
- [-] 2.3 Race (C6) pairs — **blocked on Phase 4** `race_harness_tool` (soft edge) (blocked)
- [-] 2.4 Business-logic (C5/C7) pairs — **blocked on Phase 5** `business_logic_orchestrator` (soft edge) (blocked)

### Validation Tier 1: Focused Testing
- [x] 2.5 Each pair verifies vuln-exploitable / patch-not: IDOR via the real P2 `diff()` (`gained_access` flips across the pair), SSRF via the real P0 `is_internal_target` (`tests/test_bv2p_corpus.py`) (completed)
- [x] 2.6 **Power-check:** `corpus.power_check` reports the small-gap count vs a required discordant threshold; honestly insufficient at the seed n (no tight effect size from tiny n) (completed)

### Security Readiness Checklist
- [x] 2.7 All targets run sandboxed; SSRF confirmation uses the self-hosted P3 oracle — no third-party leak (fixture + README) (completed)
- [x] 2.8 Ground-truth `V` is labeled-known-only; recall reported as recall-over-known with the unknown-unknown caveat (`ground_truth_labels` docstring + corpus module) (completed)

---

## Task Group 3 — Intervention Ablation (M3)
> The assembler is built + PBT'd in `propose-dispose-instrumentation` (TG2). This group runs its **ablation (E3)** — no Tier-2 PBT here.

### Implementation
- [ ] 3.1 E3 ablation harness: Full vs −Control vs −Knowledge vs −Checklist over the corpus (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.2 Two readouts per condition: (a) `R_prop` overall + per FN-category (C5/Knowledge, C6-C7/Checklist, C3/Control-Path) — tests H3; (b) `funnel_efficiency` with the C1-attributed FP-proposal rate broken out — tests H3b (1 check) (not_started)

### Security Readiness Checklist
- [ ] 3.3 Ablation toggles only the assembler's proposal-stage flags; the disposer and impact gate are unchanged (not_started)

---

## Task Group 4 — Single-Stage Ablation Mode (M4)  *(research-only; the one hard-gated software item)*

### Implementation
- [x] 4.1 Harness-disabled baseline (agent self-confirms) — **build-time/entrypoint gated, NEVER a runtime toggle** (`strix/research/ablation/single_stage.py` `run_self_confirm`; gated on the exact `STRIX_RESEARCH_SINGLE_STAGE_ABLATION` sentinel + research-only `__main__`) (completed)
- [~] 4.2 Static-proxy classifier baseline (`run_static_proxy`, deterministic continuous score for dynamic range); LLM-critic baseline **deferred (optional)** — `self_confirm` is the model baseline (in_progress)

### Validation Tier 1: Focused Testing
- [x] 4.3 The ablation mode produces a single-stage verdict on a fixture pair (`tests/test_single_stage_ablation.py::TestSingleStageBaselines`) (completed)

### Validation Tier 2: PBT
- [x] 4.4 PBT — **M4 production-off**: no env but the exact sentinel enables it; no production entry module imports `strix.research` (`TestProductionOff`) (completed)
- [x] 4.5 PBT — **gate neutrality**: `SingleStageVerdict` carries no `evidence_class`; ablation imports nothing from `strix.report`; the production emit path records a `confirmed` funnel verdict only with deterministic `evidence_class != none` (`TestGateNeutrality`) (completed)

### Security Readiness Checklist
- [x] 4.6 **Regression test asserting the ablation mode is OFF in the production configuration** — `test_disabled_by_default_and_runners_refuse` (completed)
- [x] 4.7 Manual verification: no production entrypoint can reach the self-confirm path — mechanized as `test_no_production_entry_module_imports_the_ablation` (completed)

---

## Task Group 5 — Experiments + Write-up (M5)

### Implementation
- [ ] 5.1 **E1** tradeoff curve (H1): sweep proposal-aggressiveness; single-stage vs propose–dispose; **watch `Prec_gate` — the most important number** (not_started)
- [ ] 5.2 **E2** gap-dictation (H2a/H2b): **gap-stratified paired McNemar PRIMARY** (strix pipeline vs single-stage proxy); difference-of-correlations + bootstrap CIs **secondary/illustrative**; report H2a (FP-arm win, margin-widens-as-gap-shrinks = mechanism fingerprint) and H2b (FN-arm = proposer recall) separately, decomposed into FP/FN-arm contributions (not_started)
- [ ] 5.3 **E3** intervention ablation (H3/H3b): see TG3 (not_started)
- [ ] 5.4 **E4** perturbation invariance (H4): semantic-preserving perturbations on the live target's responses; strix vs static-proxy verdict variance (not_started)
- [-] 5.5 Full E1–E4 including race/BL pairs — **blocked on Phases 4/5** (soft edge) (blocked)
- [ ] 5.6 Paper draft (not_started)

### Validation Tier 1: Focused Testing
- [~] 5.7 Claim→artifact traceability harness built (`strix/research/metrics.py::traceability` + `cross_check`, tested); applies to live numbers once E1–E4 run (in_progress)

### Security Readiness Checklist
- [~] 5.8 **Pre-registration drafted** (`planning/E2-preregistration.md`: gap metric, primary test, δ, power floor, no-peek) — operator sets Status: LOCKED before any E2 outcome is read (in_progress)
- [ ] 5.9 No claim imports the cited papers' magnitudes; the single-stage baseline is self-measured (M4) — enforced at write-up time (not_started)

---

> **Dedicated-check count:** TG0: 2 · TG1: 1 · TG2: 2 · TG3: 1 · TG4: 1 · TG5: 1 = **8 Tier-1** + **2 Tier-2 PBT** (4.4, 4.5) = **10** dedicated. Lean by design — a measurement track, not a new primitive; the experiments (E1–E4) are research deliverables tracked for completion, not software tests.

---

## Dependency Mapping & Critical Path

```
propose-dispose-instrumentation (funnel + assembler) ──► TG1 metrics · TG3 ablation
P0 impact_gate · P1 diff · P2 OOB · P3 reachability/classifier ──► TG0 · TG2 (IDOR/SSRF)   [ALL COMPLETE → startable now]
P4 race_harness_tool ──(soft)──► TG2.3 race pairs · TG5 race experiments        [blocked until Phase 4]
P5 business_logic_orchestrator ──(soft)──► TG2.4 BL pairs · TG5 BL experiments  [blocked until Phase 5]

        TG0 Walking Skeleton ──► TG1 Funnel ──► TG2 Corpus ──► TG3 Ablation ──► TG5 Experiments
                                                   │                              ▲
                                                   └──► TG4 Ablation-mode (research-only) ─┘
```

- **TG0** needs only P1/P2 + the funnel (consumed) — startable immediately; it is the first H2a data point.
- **TG1** consumes the instrumentation funnel (M1).
- **TG2** depends on the disposers (P1/P2 complete) for pair validation; race/BL pairs are soft-edged behind P4/P5.
- **TG3** runs the instrumentation assembler's ablation.
- **TG4** is independent research-software; it gates E1/E2/E4's baseline and carries the only hard PBT.
- **TG5** depends on TG2 (corpus) + TG3/TG4 (baselines); the full run is soft-edged behind P4/P5.

**Critical path (startable now):** `TG0 → TG2 → TG5` on IDOR/SSRF. Race/BL experiments are deferred behind their phases, not blocking the core H1/H2 result.

---

## Parallelization

- **TG4 (ablation mode)** develops in parallel with **TG2 (corpus)** — independent surfaces — then both feed TG5. With two contributors: Dev A builds the corpus (TG0→TG2), Dev B builds the guarded ablation mode (TG4); they join at TG5.
- Across specs: this `research` track runs parallel to Phase 4 and to the `instrumentation` unit's TG2/TG3 — no shared build surface.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG0 Walking Skeleton | 1 |
| TG1 Funnel Consumption | 0.5 |
| TG2 B-V2P Corpus (IDOR/SSRF; race/BL deferred) | 2 |
| TG3 Intervention Ablation | 1 |
| TG4 Single-Stage Ablation Mode | 1 (parallel with TG2) |
| TG5 Experiments + Write-up | 3 |
| **Total (core, sequential)** | **~8.5 iterations** |
| **Race/BL pairs + full run** | deferred behind Phases 4/5 (soft edges) |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 validation checks pass (funnel cross-check, per-pair exploitability, claim→artifact traceability).
- [ ] **Gate 3** — the **Tier-2 PBT invariants validated**: M4 production-off (4.4) + gate neutrality (4.5). *(These are the locus-1 guarantees; the spec's other ∀ invariants — funnel completeness, no-third-party-leak — are owned/validated in the instrumentation unit and Phase 2.)*
- [ ] **Gate 4 (research validity)** — pre-registration of E2's gap metric, test, and δ before outcomes; recall reported as recall-over-known with the unknown-unknown caveat; no imported magnitudes; M4 confirmed off in production config.
