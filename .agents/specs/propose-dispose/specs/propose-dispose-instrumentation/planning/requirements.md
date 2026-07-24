# Propose–Dispose Instrumentation — Planning / Requirements

> Conceptual grounding for the `propose-dispose-instrumentation` spec. Owned by PM/architect + author; the coder implements from `spec.md` + `tasks.md`. This file records *why*, so the reasoning is not reconstructed in the implementation session.

## Origin

Extracted from the propose–dispose research proposal (v0.4) §4.1 (funnel) and §4.3 (proposal interventions). These two pieces are **product-reusable engine capability** — pipeline observability and a recall-raising proposal layer — so they live in the product DAG as a `unit`, separate from the research execution (`propose-dispose-validation`). They survive even if the paper is never written.

## What problem this solves

1. **Unmeasurable pipeline.** Without a funnel, `R_prop`, `Prec_gate`, `R_e2e`, and `funnel_efficiency` cannot be computed, so the core thesis (the deterministic disposer breaks the precision/recall trade) is unfalsifiable. The funnel is the substrate every research metric reads — build it once, in the product, additively.
2. **Recall ceiling at the proposer.** The harness cannot confirm what the agent never proposes. Per the v0.4 H2 split, gap-dictation relocates from the disposer to the proposer and reappears as false negatives. The assembler raises proposal recall by attacking the Semantic Trap's FN-drivers (C5/C6/C7) at proposal time — without touching what gets confirmed.

## Requirements rationale (maps to spec.md F-1…F-8)

- **F-1/F-2 (funnel + metrics):** additive to `report/state.py`; the impact gate is the one thing we never touch. ProposalRecord must carry `evidence_class` per harness verdict because that is the join key between a proposal and its disposition — the whole decomposition `R_e2e = R_prop · (|C∩V|/|P∩V|)` is computed from it.
- **F-3 Control-Path:** rides the just-merged P3 `reachability_seam`. Targets **C3** (scope/context) for recall; its **C1** effect (control-flow FP reduction) is billed to `funnel_efficiency`, not recall (v0.4 §4.3 C1/C2 symmetry). Must be bounded/compact (VulTriage multi-granularity lesson) or it floods context.
- **F-4 Knowledge-Path:** keyed by the P3 `parameter_classifier` class; targets **C5** (CWE misapplication — the single most frequent FN-driver).
- **F-5 C-checklist:** targets **C6** (concurrency) + **C7** (trust boundary, FN side). Recall-oriented: lowers the bar to propose; the gate absorbs the extra noise.
- **F-6 ablation:** each intervention has its own flag so E3 (in the research spec) can ablate cleanly; the flag matrix is recorded per ProposalRecord.
- **F-7/F-8 (glass-box + boundary):** the load-bearing safety requirement. The assembler is proposal-stage only — it sets no `evidence_class` and writes no report state. This is the locus-1 guarantee (`AGENTS.project.md`: "the agent proposes; the harness disposes") enforced in code, tested by PBT invariant 2.

## Key decisions already made (do not re-litigate in implementation)

- **Two specs, not one phase.** This `unit` is the buildable half; the research half is `propose-dispose-validation`. The single-stage ablation mode (M4) is NOT here — it stays quarantined in the research spec, never in the product capability DAG.
- **C-category targeting is FN-driven.** Recall interventions target C5/C6/C7 (FN-drivers), not C1/C2 (FP-drivers). FP-drivers are credibility-safe and only a funnel-efficiency cost — already settled in v0.4 §4.3; the coder should not re-derive the mapping.
- **Disposer untouched.** P2 diff / P3 OOB / P4 race / impact gate are not modified. The funnel observes; it adds no evidence class.
- **Determinism boundary.** Control-Path verbalization and Knowledge priors are deterministic given their inputs; the checklist questions are fixed. The only model-driven step is the agent's proposal — preserved.

## Dependencies (both satisfied)

- **Phase 0** — `impact_gate` / `report/state.py` (funnel rides here).
- **Phase 3** — `reachability_seam` (Control-Path source) + `parameter_classifier` (Knowledge key); both merged to `main` and wired into `_BASE_TOOLS` as of the Phase 3 close-out (`548915f` → squash `ce731a5`).

## Sequencing note

TG1 (funnel) is independently shippable and is the only thing the research spec's M0/M1 strictly need — land it first if schedule-pressed. TG2 (the recall layer) feeds research E3 but is not on the M0 critical path. This `unit` runs parallel to Phase 4.

## Explicit non-goals (so they are not pulled in)

- No experiments, no B-V2P corpus, no single-stage ablation mode (all in `propose-dispose-validation`).
- No new harness, no new evidence class, no change to the agent's proposal *decision*.
- No FP-driver elimination as a recall objective.
