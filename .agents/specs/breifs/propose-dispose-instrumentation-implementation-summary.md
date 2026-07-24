# Propose–Dispose Instrumentation (Spec A · F-PD-A) — Implementation Summary for the PM Validator

**Spec:** `.agents/specs/propose-dispose/specs/propose-dispose-instrumentation/{spec.md,tasks.md}`
**Kickoff:** `.agents/specs/propose-dispose/propose-dispose-instrumentation-kickoff.md`
**Branch:** `propose-dispose` → `origin/propose-dispose @ f4b9637` (pushed; local == remote)
**Producer:** `claude-kimi-k2p7-code` · **Status:** `in_review` (producer hand-off; not self-validated)
**Date:** 2026-06-17

> Single-sentence framing: the funnel turns `proposal → harness → confirmation → report` into a glass box,
> and the assembler raises proposal recall **without ever touching precision** — the proposer proposes, the
> harness disposes. The whole spec is **additive instrumentation** on the existing `report/state.py`; the
> impact gate and `vulnerability_reports` semantics are unchanged.

---

## 1. Commits on the branch (vs `main`)

| Commit | Scope |
|---|---|
| `f51939f` | TG1 — `ProposalRecord` + `FunnelLog` + derived metrics + tests |
| `7f01b35` | TG2 assembler + TG3 integration (proposal tool wired into `factory._BASE_TOOLS`) |
| `f4b9637` | Disposer→funnel **live wiring** (additive); +`tests/test_proposals_disposer_wiring.py` |

Cumulative vs `main`: **13 files, +1344 / −2**.

---

## 2. What was implemented, by contract

### Contract A — Funnel / ProposalRecord (measurement substrate)
- `strix/core/proposals/models.py` — `ProposalRecord` (endpoint/param ref, agent CWE, C1–C8 answers,
  harnesses selected, per-harness `HarnessVerdict` = verdict + `evidence_class`, timing/cost,
  `InterventionFlags` matrix; append-only `add_verdict`/`attach_report`/`record_context`). All models
  `extra="forbid"`.
- `strix/report/proposals.py` — `FunnelLog` (append-only, in-memory index, JSON persist/load) + four **pure**
  derived metrics: `compute_r_prop`, `compute_prec_gate`, `compute_r_e2e`, `compute_funnel_efficiency`
  (external label set `V` supplied as `set[str]`).
- `strix/report/state.py` — additive hook: `self.funnel_log`, hydrate/save `funnel.json`. Impact gate +
  `add_vulnerability_report` semantics unchanged.

### Contract B — Proposal-Context Assembler (flag-gated recall layer)
- `strix/core/proposals/assembler.py` — `assemble_proposal_context(endpoint, param, flags, checklist)`:
  composes only enabled streams, records the active `InterventionFlags` into the returned `ProposalContext`.
  - Control-Path `_verbalize_control_path` — P3 `reachability_seam` → one bounded line per layer (no graph dump).
  - Knowledge-Path `_build_knowledge_path` + `_KNOWLEDGE_PRIORS` — CWE prior keyed by P3 param class.
  - C1–C8 `models.C1C8Checklist.default_questions` — fixed FN-driver questions (C3/C5/C6/C7); only answers vary.
  - **Sets no `evidence_class`; writes no report state.**

### Contract C — Integration & live wiring
- `strix/tools/inventory/tools.py::propose_vulnerability_investigation` (wired in `strix/agents/factory.py`):
  reads ranked map, assembles context, appends to `funnel_log` via `start_proposal`, persists glass-box.
  Never runs a harness, never sets `evidence_class`.
- **Disposer→funnel live wiring (`f4b9637`):** `ReportState.add_vulnerability_report` →
  `_link_disposer_verdict_to_funnel` additively records a `confirmed` `HarnessVerdict` (with the realized
  `evidence_class`) + links the `report_id` onto the matching `ProposalRecord`. Correlation: explicit
  `proposal_id` preferred, else conservative single-endpoint match (`_match_open_proposal`);
  `evidence_class="none"` → skipped. Optional `proposal_id` threaded through `create_vulnerability_report`
  + `_do_create` (`strix/tools/reporting/tool.py`). **Harness tools P2/P3/P4 untouched.**

---

## 3. The locus-1 safety boundary (what to TRACE, not just re-run)

`evidence_class` is constructed in exactly one funnel path: `FunnelLog.record_harness_verdict`
(`strix/report/proposals.py`), reachable only from the disposer side (`_link_disposer_verdict_to_funnel`,
itself only fired after a harness verdict reaches `add_vulnerability_report`). The proposal stage
(`assemble_proposal_context` / `propose_vulnerability_investigation`) has **no branch** that sets
`evidence_class`, builds a `HarnessVerdict`, writes a `vulnerability_report`, or mutates `ReportState`
beyond appending to `funnel_log`. `ProposalContext` carries no evidence/verdict field.

**Suggested validator trace:** grep `evidence_class` and `add_vulnerability_report` across `strix/`; confirm
every hit is either a harness output or the single funnel constructor, and none is reachable from the
proposal-stage call graph.

---

## 4. Mandatory PBT invariants (assert structural meaning)

| Invariant | Test |
|---|---|
| 1.6 funnel completeness | `tests/test_proposals_funnel.py::test_completeness` (Hypothesis) |
| 2.7 assembler boundary (safety-critical) | `tests/test_proposals_assembler.py::test_no_report_state_mutation` (+ code trace, §3) |
| 2.8 ablation independence | `tests/test_proposals_assembler.py::test_ablation_independence` |
| 2.9 determinism | `tests/test_proposals_assembler.py::test_stable_outputs` (Hypothesis) |

Disposer-wiring tests (`tests/test_proposals_disposer_wiring.py`, 6): explicit-`proposal_id` link;
best-effort endpoint match; `none`→no verdict; ambiguous→no-op; no re-match of a closed proposal;
additivity (no proposals ⇒ report byte-faithful, `impact_gate_decision` unchanged).

---

## 5. Gate (whole repo, last run)

```
ruff check .            → All checks passed
ruff format --check .   → 195 files already formatted
mypy strix/             → 0 errors (153 files)
pyright strix/          → 0 errors, 0 warnings
bandit -r strix/        → 0 issues (H/M/L all 0)
pytest tests/ -q        → 334 passed, 4 skipped (Docker), 19 subtests
                          (19 dedicated proposal tests: funnel 3 / assembler 8 / integration 2 / wiring 6)
```

Additivity spot-check: the 33 report/gate/impact tests pass unchanged.

---

## 6. Open / deferred (flagged for the validator, not blockers)

1. **Unconfirmed harness runs are not recorded live.** Only confirmed verdicts (those reaching a report) are
   linked in the running pipeline. Capturing unconfirmed harness runs (e.g. an OOB candidate that never
   correlates) would require editing the harness tools — intentionally out of the "disposer unchanged" scope
   for Spec A. Funnel completeness (1.6) still holds for proposals that reach a confirmed verdict.
2. **Evidence-set width.** Implementation uses a 5-way set incl. `race_result`; the spec invariant *text*
   lists a 4-way subset. The implementation is a sound superset (P4 race landed); spec-text alignment only.

---

## 7. Validation checklist (recommended)

- [ ] Trace the locus-1 boundary in code (§3) — confirm no proposal-stage path sets `evidence_class`/writes report state.
- [ ] Confirm `report/state.py` is strictly additive — impact gate + `vulnerability_reports` byte-identical (`git diff origin/main..f4b9637 -- strix/report/state.py`).
- [ ] Confirm the disposer wiring touches no harness tool (`git show f4b9637 --stat` = state.py + reporting/tool.py + new test only).
- [ ] PBTs 1.6 / 2.7 / 2.8 / 2.9 present and meaningful (not tautological).
- [ ] Re-run the full gate (§5).
- [ ] Issue `verdict.md` in `.agents/specs/propose-dispose/specs/propose-dispose-instrumentation/validation/`.

> Source completion report: `.agents/.../propose-dispose-instrumentation/validation/completion-report.md`
> (this summary consolidates it + the `f4b9637` wiring for hand-off). `.agents/` is local-only (gitignored);
> code is on `origin/propose-dispose @ f4b9637`.
