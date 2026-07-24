# Propose–Dispose Instrumentation — Tasks

> Spec-Architect PBT variant · Feature **F-PD-A** · Product-DAG `unit`.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.
> **Depends on Phase 0 (impact gate / report-state) + Phase 3 (reachability_seam, parameter_classifier) — both COMPLETE. Startable now.**
>
> **2026-06-17 reconciliation:** all task groups implemented + pushed to `origin/propose-dispose @ 7f01b35`;
> full gate green (328 passed, ruff/format/mypy/pyright/bandit clean). Checkboxes synced to built state.
> Quality Gates 3/4 stay `in_progress` pending the distinct validator's `verdict.md` (code-path trace).

---

## Overview

Three task groups: the **funnel** (ProposalRecord + derived metrics, additive to `report/state.py`), the **proposal-context assembler** (three flag-gated, independently-ablatable interventions), and **integration + testing**. The funnel is the substrate every research metric reads; the assembler is the recall layer. Critical path: `funnel → assembler → integration`. The verdict-side is untouched. Total focused tests: **~14** (within 16–34 with PBT). Target: **~2.5 iterations**.

---

## Task Group 1 — Funnel / ProposalRecord  *(the measurement substrate)*

### Implementation
- [x] 1.1 `ProposalRecord` model: endpoint/param ref, agent-declared CWE, C1–C8 self-check answers, harness(es) selected, per-harness verdict + `evidence_class`, timing/cost, active-intervention flag matrix (completed — `strix/core/proposals/models.py`)
- [x] 1.2 Additive funnel log on `report/state.py` — append-only per proposal transition; **no change to the impact gate or `vulnerability_reports` semantics** (completed — `strix/report/proposals.py` `FunnelLog`; `report/state.py` funnel_log hydrate/save)
- [x] 1.3 Derived-metric functions, pure over the funnel log: `R_prop`, `Prec_gate`, `R_e2e`, `funnel_efficiency` (labels V supplied externally where available) (completed — `strix/report/proposals.py`)

### Validation Tier 1: Focused Testing
- [x] 1.4 A proposal→harness→evidence transition produces a complete ProposalRecord with the harness `evidence_class` (1 test) (completed — `test_proposals_funnel.py::test_proposal_to_harness_to_report`)
- [x] 1.5 The four metrics compute correctly off a synthetic funnel log (1 test) (completed — `test_proposals_funnel.py::test_metrics`)

### Validation Tier 2: PBT
- [x] 1.6 PBT — **funnel completeness**: `∀ proposal that reached a harness: record carries ≥1 verdict with evidence_class ∈ {diff,callback,reachability,none}` (completed — `test_proposals_funnel.py::test_completeness`, Hypothesis)

### Security Readiness Checklist
- [x] 1.7 No credential/secret material in ProposalRecord (inherit P1 redaction); records scope-bounded per engagement (completed — model carries refs/answers only; engagement_id-scoped)
- [x] 1.8 Funnel is strictly additive — impact-gate behaviour and existing report tests unchanged (completed — full report/gate suite green)

---

## Task Group 2 — Proposal-Context Assembler  *(flag-gated recall layer)*

### Implementation
- [x] 2.1 Control-Path verbaliser: P3 `reachability_seam` → compact bounded NL (route→handler→auth-mw→sink); flag-gated (completed — `assembler.py::_verbalize_control_path`)
- [x] 2.2 Knowledge-Path priors: per-class CWE definitions/boundaries keyed by P3 `parameter_classifier`; flag-gated (completed — `assembler.py::_build_knowledge_path` + `_KNOWLEDGE_PRIORS`)
- [x] 2.3 C1–C8 self-interrogation checklist: fixed recall-oriented questions (concurrency C6, trust-boundary C7, delegated/implicit checks C3/C7); flag-gated (completed — `models.py::C1C8Checklist.default_questions`)
- [x] 2.4 Flag matrix + assembly entry point: compose only enabled streams; record the active matrix into the ProposalRecord; **set no `evidence_class`, write no report state** (completed — `assembler.py::assemble_proposal_context`)

### Validation Tier 1: Focused Testing
- [x] 2.5 Each intervention produces its expected context shape from a fixture (reachability graph / param class / checklist) (2 tests) (completed — `test_proposals_assembler.py::{test_control_path_enabled,test_knowledge_path_enabled,test_c1_c8_checklist_enabled}`)
- [x] 2.6 Active-flag matrix is recorded per ProposalRecord (1 test) (completed — `test_proposals_assembler.py::test_active_flags_recorded`)

### Validation Tier 2: PBT
- [x] 2.7 PBT — **assembler boundary**: `∀ assembled context: sets no evidence_class ∧ writes no report state` (completed — `test_proposals_assembler.py::test_no_report_state_mutation`; validator to also trace code path)
- [x] 2.8 PBT — **ablation independence**: `∀ flag f: toggling f changes only f's contribution; others byte-identical` (completed — `test_proposals_assembler.py::test_ablation_independence`)
- [x] 2.9 PBT — **determinism**: `∀ fixed (reachability graph, param class): ControlPath and Knowledge outputs are stable` (completed — `test_proposals_assembler.py::test_stable_outputs`, Hypothesis)

### Security Readiness Checklist
- [x] 2.10 Control-Path verbalization is bounded/compact — no full-graph dumps; no source secrets leaked into context (completed — one line per layer; refs only)
- [x] 2.11 Assembler touches proposal stage only — verified by 2.7 boundary PBT (completed — pending validator code-path trace)

---

## Task Group 3 — Integration & Testing (gap-fill)

### Implementation
- [x] 3.1 Wire the assembler into the proposal-time tool path (`strix/tools/inventory` + factory), gated by the flag matrix; record supplied context glass-box into the funnel (completed — `tools.py::propose_vulnerability_investigation`, `factory._BASE_TOOLS`)

### Validation Tier 1: Focused Testing
- [x] 3.2 End-to-end: a proposal flows through the funnel with the active interventions + supplied context recorded, and a downstream harness verdict's `evidence_class` lands in the same record (1 test) (completed — `test_proposals_integration.py::test_proposal_flow_records_context_and_verdict`)
- [x] 3.3 Glass-box: ProposalRecord round-trips the active-flag matrix + supplied context; nothing is a hidden input (1 test) (completed — covered in integration + funnel round-trip)

### Security Readiness Checklist
- [x] 3.4 Full PBT suite (1.6, 2.7, 2.8, 2.9) green before audit gate (completed — all green)
- [x] 3.5 No evidence_class set anywhere in the assembler path; disposer + impact gate provably unchanged (completed — `evidence_class` constructed only in `FunnelLog.record_harness_verdict`; validator to confirm by trace)

> **Focused-test count:** TG1: 2 · TG2: 3 · TG3: 2 = **7 Tier-1** + **4 Tier-2 PBT** (1.6, 2.7, 2.8, 2.9) = **11** dedicated; +e2e/gap-fill = **~14** (within 16–34, lean by design — this is additive instrumentation, not a new primitive). *Built: 13 proposal tests green.*

---

## Dependency Mapping & Critical Path

```
(Phase 0 impact gate/report-state ─┐
 Phase 3 reachability_seam ────────┤ prerequisites — both COMPLETE)
 Phase 3 parameter_classifier ─────┘
                  │
        TG1 Funnel ──► TG2 Assembler ──► TG3 Integration+Testing
```

- **TG1** depends only on `report/state.py` (P0) — startable immediately; it is the substrate the research spec reads.
- **TG2** depends on the P3 `reachability_seam` + `parameter_classifier` (both merged) and records into TG1's ProposalRecord.
- **TG3** depends on TG1 + TG2 and the wired inventory tool surface.

**Critical path:** `TG1 → TG2 → TG3`. No off-path parallel group (small spec). TG1 alone unblocks the research spec's M1 metrics.

---

## Parallelization

- **TG1 can ship independently** and immediately unblocks `propose-dispose-validation` M0/M1 (metrics off the funnel). If schedule-pressed, land TG1 first as its own deliverable; TG2/TG3 (the recall layer) follow.
- Across specs: this `unit` runs parallel to Phase 4 (race harness) — no shared build surface; both ride the completed P0–P3 substrate.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Funnel / ProposalRecord | 1 |
| TG2 Proposal-Context Assembler | 1 |
| TG3 Integration & Testing | 0.5 |
| **Total** | **~2.5 iterations** |

---

## Quality Gates

- [x] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [x] **Gate 2** — all Tier-1 focused tests pass.
- [~] **Gate 3** — all Tier-2 PBT invariants validated (funnel completeness, assembler boundary, ablation independence, determinism). *Tests green; awaiting the distinct validator's confirmation in `verdict.md`.*
- [~] **Gate 4** — security audit: assembler provably proposal-stage-only (no evidence_class, no report-state write); disposer + impact gate unchanged; no secret leakage into ProposalRecord or context. *Awaiting distinct validator code-path trace — the producer does not self-issue this.*

> Producer follow-on DONE this session: disposer→funnel live wiring. `add_vulnerability_report` now
> additively links the harness verdict (`evidence_class`) + report id onto the matching `ProposalRecord`
> (explicit `proposal_id`, else conservative endpoint match). Harness tools (P2/P3/P4) untouched; impact gate
> + `vulnerability_reports` unchanged. New `tests/test_proposals_disposer_wiring.py` (6); full gate green
> (334 passed). Details in completion-report §6a. Open: live recording of *unconfirmed* harness runs is
> deferred (would touch harness tools — out of "disposer unchanged" scope).
