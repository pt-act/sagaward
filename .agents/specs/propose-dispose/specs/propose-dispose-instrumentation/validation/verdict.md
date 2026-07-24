# Verdict — propose-dispose-instrumentation (Spec A) — round 1

## Header
spec_id: propose-dispose-instrumentation (F-PD-A, product-DAG `unit`)
validator: opus-4.8-pm-auditor
producer: opus-4.8 (separate instance, independent context) — **NOT** `claude-kimi-k2p7-code` (the summary's label is the stale harness identifier; the real producer is an Opus 4.8 instance)
validator_distinct_from_producer: **false** — same model, different instance. **Operator-approved override** (operator owns this §B distinctness decision). Consequence: this verdict is **method-carried, not lineage-carried** — every finding below rests on an executed check, a traced call graph, or a type-structure fact (all lineage-independent), not on "I reason differently than the producer."
reviewed_commit: origin/propose-dispose @ f4b9637
verdict_timestamp: 2026-06-17
method: §C + v2.1 boundary trace.

## Decision
status: approved — with one operator decision required before Spec B (funnel completeness scope), and two minor notes.

## Verified (independently)
- **Scope.** `git diff --stat origin/main..f4b9637` = **13 files, +1344/−2**, exactly the summary's claim. New `strix/core/proposals/` module + `report/proposals.py` (FunnelLog + 4 pure metrics) + additive `report/state.py` hook + the proposal tool + 4 test files. **No harness-tool changes** (no diff/oob/race tool diffs) — the "disposer unchanged" constraint holds at the scope level.
- **Locus-1 boundary (safety-critical) — confirmed structurally + by call-graph trace.** `ProposalContext` carries **no `evidence_class` / verdict field** (only `control_path_nl`, `knowledge_path_nl`, `c1_c8_checklist`, `active_flags`; `extra="forbid"`). `assemble_proposal_context` takes **no `ReportState`**. The lone `evidence_class` constructor, `FunnelLog.record_harness_verdict`, is called from **exactly one site** (`report/state.py:315`, inside the disposer-link path) — **unreachable from the proposal stage**. `assembler.py` / `propose_vulnerability_investigation` reference `evidence_class`/`ReportState` only in docstrings. The proposer structurally cannot confirm.
- **Additivity.** `report/state.py`'s only deletion is a benign signature widening (`set_global_report_state` gained `| None`); the impact gate + `add_vulnerability_report` semantics are unchanged, and the existing report/impact-gate tests pass unchanged (28 proposal+gate tests green).
- **Full gate (re-run).** **334 passed, 4 skipped, 19 subtests** (= 315 + 19 proposal tests). `ruff` clean; `mypy --strict` clean on the proposals module (4 files).
- **PBTs present.** funnel completeness, ablation independence, determinism — all green.

## Issues / notes

1. **Operator decision required before Spec B — funnel completeness is CONFIRMED-ONLY (severity: major, spec-tension → operator).**
   Invariant 1.6 / F-1 says *"∀ proposal that reached a harness: record carries ≥1 verdict."* The implementation records only **confirmed** verdicts (those reaching a report); an **unconfirmed** harness run (e.g. an OOB candidate that never correlates) is not recorded. So the funnel-completeness PBT validates a *narrowed* property (confirmed subset), not the full "reached a harness" population. **Downstream impact:** `Prec_gate = |C∩V|/|C|` and `funnel_efficiency = harness_runs/|C|` will be **biased** — `|C|`/`harness_runs` undercount the unconfirmed runs — which matters for Spec B's experiments. This is **honestly disclosed** (summary §6.1) and is bounded by the locked "disposer unchanged" decision (capturing unconfirmed runs requires a hook in the harness tools). **It does not block Spec A** — the producer correctly honored the disposer-unchanged constraint and the confirmed-path funnel is sound. But before Spec B's metrics are trusted, the **operator must decide**: (a) add a minimal *additive* emit-hook in the harness tools that records every run (confirmed or not) without changing disposer logic, or (b) accept the bias and document the metric as confirmed-only. Routes to operator because it's a spec-constraint tension, not an implementation error.

2. **Boundary PBT 2.7 is borderline-tautological (minor).** `test_no_report_state_mutation` calls `assemble_proposal_context` without ever passing it a `ReportState`, then asserts that an unrelated `ReportState` is unchanged — which is trivially true. The boundary is genuinely carried by **structure** (`ProposalContext` has no evidence field; the assembler takes no `ReportState`) and the **call-graph trace**, both of which I confirmed — so the guarantee holds. But strengthen the test to assert the structural property directly (e.g., `"evidence_class" not in ProposalContext.model_fields`, or that the proposal-stage call graph contains no `record_harness_verdict`/`add_vulnerability_report`) so it's not relying on an object it never touches. Producer honestly flagged the test leans on the §3 trace.

3. **Evidence-set spec-text drift (minor).** Implementation uses the 5-way `{diff, callback, reachability, race_result, none}`; the spec invariant *text* lists the 4-way subset. The implementation is the correct superset (P4 race landed). Update the spec text to match — alignment only.

## Provenance
Record the real producer (`opus-4.8`, separate instance) in the manifest `execution.producer`, not the stale `claude-kimi-k2p7-code` harness label, so the audit trail is honest about the same-model pairing the operator approved.

## Verdict rationale
Spec A is clean, additive instrumentation that honors its hardest constraint — the proposer can never confirm — and enforces it in *type structure*, not convention (the strongest possible form). Scope is exactly as claimed, the disposer is untouched, additivity holds, and the gate is green and reproduced. The one substantive item — confirmed-only funnel completeness — is an honestly-disclosed spec-tension that biases Spec B's metrics; it does not block Spec A but needs an operator ruling before the research experiments run. Decision: **approved.** Eligible to flip to `approved` in the manifest; TG1's funnel unblocks Spec B's M0/M1 (with the completeness caveat noted).

## Session Manifest
- Skill: pm-auditor@2.1 · validator
- Spec: propose-dispose-instrumentation · `unit`
- validator_distinct_from_producer: false (operator-approved same-model override) — findings are executable/structural, lineage-independent
- Commit: f4b9637 (clean vs origin)
- Verified: scope, locus-1 boundary (structure + trace), additivity, full gate (334 passed), static gate on proposals
- Decision: approved (1 major→operator, 2 minor)
- Prior conflict: no — no arbiter
- Recommendation: third-lineage arbiter (Kimi/Gemini) or Locus-3 for anything contested, given the same-model pair
