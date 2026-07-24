# Bringing Propose–Dispose into the manifest — architecture + draft entries

**For:** operator → coder (coder maintains `manifest.yml` + `.agents/specs/`)
**From:** PM/architect
**Decision:** Yes, formalize it — but as **two specs of different types**, not one product phase. Reasoning first, then drop-in entries.

---

## Why not a single "phase-6"

The manifest's DAG is a **build-dependency graph of engine capabilities**: each `unit`/`integration` spec *produces* an interface that a later spec *consumes*, and milestones gate the product. The propose–dispose program does not fit that shape as one node, because it is **two kinds of work fused in one proposal**:

1. **Buildable engine capability** (M1 funnel instrumentation + M3 proposal-context assembler) — real, product-reusable features: pipeline observability, and a recall-raising proposal layer. These belong **in the product DAG**.
2. **Research execution** (M2 B-V2P corpus + M4 research-only ablation mode + M5 experiments/paper) — a validation track that *measures* the engine. This is **not a capability the product needs to function**, must **not gate product milestones**, and contains the one component (M4 self-confirm) that is explicitly forbidden in production.

Collapsing these into "phase-6" would (a) imply the product isn't done until the research runs (false), (b) drag the forbidden M4 ablation mode into the product DAG, and (c) misrepresent a cross-cutting consumer of phases 0–5 as the next link in a chain. So: **split it.**

---

## Recommended structure: two specs

### Spec A — `propose-dispose-instrumentation` · `type: unit` · **in the product DAG**
The genuinely product-reusable parts. Survives even if the paper is never written.
- **Produces:** funnel/`ProposalRecord` telemetry (M1); the flag-gated proposal-context assembler (M3 — Control-Path verbalization + Knowledge priors + C-checklist, the recall-raising layer).
- **Consumes:** `impact_gate` (P0), `reachability_seam` + `parameter_classifier` (P3).
- **Has tasks + tests** like any phase: the funnel is additive-to-`report/state.py` and unit-testable; the assembler is flag-gated/ablatable; M3's interventions map to the FN-driver C-categories (C5/C6/C7) per the v0.4 split.

### Spec B — `propose-dispose-validation` · `type: research` (new type) · **parallel track, non-gating**
The research execution. Consumes the instrumentation + the phase artifacts it measures.
- **Produces:** B-V2P corpus (M2); single-stage ablation mode (M4 — **research-only, build-time/entrypoint gated, off-in-prod test**); experiment results + paper (M5).
- **Consumes:** Spec A's instrumentation; `differential_engine` (P1), OOB/`inject_confirm_tool` (P2), `race_harness_tool` (P4), `business_logic_orchestrator` (P5).
- **Tracked, not PBT'd:** hypotheses are the research analog of requirements; experiments are deliverables. Only the *software* pieces (the M4 off-in-prod guardrail test) get a hard gate.

This keeps M4 (the forbidden self-confirm path) quarantined in a research spec that never enters the product capability graph, and puts the keep-forever value (telemetry + better proposals) in the DAG.

---

## Dependency-encoding nuance (important for honest DAG)

The manifest's `depends_on` is **spec-level (hard, start-blocking)**; `consumes` is the **interface edge**. The research track can *start now* (M0/M1 need only P1/P2/P3, all complete) but some experiments need P4/P5. Encode that honestly:
- `depends_on` = the **minimum to start** (phases 0–3, all completed) — so the manifest shows it as startable, not falsely blocked on P4/P5.
- `consumes` **includes** `race_harness_tool` (P4) and `business_logic_orchestrator` (P5), with a note that those edges gate only the **race / business-logic B-V2P pairs** (M2) and the **full E1–E4 run** (M5), not the whole spec.

Same for Spec A: `depends_on: [phase-0, phase-3]` (both complete) → startable now; M3 rides on the just-merged Phase 3 reachability/param work.

---

## Draft manifest entries (for the coder to add to `specs:`)

```yaml
  - id: propose-dispose-instrumentation
    title: Propose–Dispose Instrumentation (funnel + proposal-context)
    type: unit
    status: planned
    file: .agents/specs/propose-dispose-instrumentation/spec.md
    depends_on: [phase-0-foundation-hardening, phase-3-attack-surface-inventory]
    produces:
      - name: funnel_log
        shape: "additive report-state record{endpoint/param ref, declared CWE, C1-C8 self-check, harness(es) selected, per-harness verdict+evidence_class, timing/cost} — product-reusable telemetry"
        consumers: [propose-dispose-validation]
      - name: proposal_context_assembler
        shape: "flag-gated assembler{control-path verbalization, knowledge CWE priors, C1-C8 checklist} → proposal-time context; targets FN-drivers C5/C6/C7; ablatable"
        consumers: [propose-dispose-validation]
    consumes:
      - name: impact_gate
        from: phase-0-foundation-hardening
      - name: reachability_seam
        from: phase-3-attack-surface-inventory
      - name: parameter_classifier
        from: phase-3-attack-surface-inventory

  - id: propose-dispose-validation
    title: Propose–Dispose Validation (B-V2P benchmark + experiments)
    type: research            # new spec type: validation/measurement, non-gating
    status: planned
    file: .agents/specs/propose-dispose-validation/spec.md   # canonical: propose-dispose-research-proposalV0.4.md
    depends_on: [phase-0-foundation-hardening, phase-1-identity-differential, phase-2-oob-oracle, phase-3-attack-surface-inventory]
    produces:
      - name: bv2p_corpus
        shape: "labeled dockerized {vuln-commit, patch-commit} deployment pairs, ≥1 per primitive, minimal-diff; ground-truth V"
        consumers: []
      - name: single_stage_ablation_mode
        shape: "RESEARCH-ONLY harness-disabled baseline (agent self-confirms); build-time/entrypoint gated; regression test asserts OFF in prod config"
        consumers: []
      - name: experiment_results
        shape: "E1 tradeoff-curve, E2 gap-dictation (gap-stratified paired McNemar primary), E3 intervention ablation, E4 perturbation invariance + paper draft"
        consumers: []
    consumes:
      - name: funnel_log
        from: propose-dispose-instrumentation
      - name: proposal_context_assembler
        from: propose-dispose-instrumentation
      - name: differential_engine
        from: phase-1-identity-differential
      - name: inject_confirm_tool
        from: phase-2-oob-oracle
      - name: race_harness_tool        # soft edge: gates only the race B-V2P pairs / E-runs
        from: phase-4-race-harness
      - name: business_logic_orchestrator   # soft edge: gates only the business-logic B-V2P pairs / E-runs
        from: phase-5-business-logic-testing
      - name: impact_gate
        from: phase-0-foundation-hardening
```

## Draft milestone (add to `milestones:`, after the product milestones)

```yaml
  - name: propose-dispose-validated
    specs: [propose-dispose-instrumentation, propose-dispose-validation]
    status: not_started
    gating: parallel        # NON-gating to product milestones; this is a measurement track
    note: "Research/validation track. Startable now (deps P0-P3 complete); race/BL experiments light up as P4/P5 land. Must never block product milestones."
```

---

## Spec-file structure (mirror the phase triplet)

For **Spec A** (`propose-dispose-instrumentation/`): full phase rigor — `spec.md` (Goal/requirements/PBT/out-of-scope/Gate 1), `tasks.md` (TG1 funnel, TG2 assembler, TG3 tests), `planning/requirements.md`. The buildable parts deserve the same treatment as a phase.

For **Spec B** (`propose-dispose-validation/`): **keep the v0.4 proposal as the canonical `spec.md`** — it already has Goal/thesis, falsifiable hypotheses (= requirements), method, experiments, threats-to-validity, M0–M5 plan, paper framing. It is *more* rigorous than a typical spec; don't flatten it. Add a thin `tasks.md` mapping M0–M5 to task groups (M0 walking skeleton, M2 corpus build, M4 ablation-mode-with-guardrail, M5 experiment runs) and note which carry hard gates (only M4's off-in-prod test) vs. which are research deliverables.

---

## Net recommendation
Two specs: `propose-dispose-instrumentation` (`unit`, in the DAG, product-reusable) and `propose-dispose-validation` (`research`, parallel, non-gating). This is the structure that (1) keeps the keep-forever engine value in the product graph, (2) quarantines the forbidden M4 self-confirm mode out of the product capability set, (3) encodes the cross-cutting P4/P5 consumption honestly as soft edges, and (4) gives the buildable parts the same spec+PBT discipline the phases got while not pretending the paper is a product gate.
