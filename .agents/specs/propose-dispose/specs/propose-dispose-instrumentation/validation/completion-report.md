# Propose–Dispose Instrumentation (Spec A · F-PD-A) — Completion Report

**Branch:** `propose-dispose`
**Commit:** `origin/propose-dispose @ 7f01b35` (superset of `propose-dispose-instrumentation @ f51939f`, TG1-only)
**Date:** 2026-06-17
**Producer:** `claude-kimi-k2p7-code`
**Spec:** `.agents/specs/propose-dispose/specs/propose-dispose-instrumentation/{spec.md,tasks.md}`
**Kickoff:** `.agents/specs/propose-dispose/propose-dispose-instrumentation-kickoff.md`

> Note: this report was reconciled on resume. The code for all three task groups was implemented and
> pushed to `origin/propose-dispose` and is gate-green, but the completion report and memory_bank
> tracking had not been filed. This document closes that gap and hands the spec to the distinct
> validator. No code was changed during reconciliation.

---

## 1. What was built (by contract)

### Contract A — Funnel / ProposalRecord (the measurement substrate)

| Task | Evidence | Status |
|---|---|---|
| 1.1 `ProposalRecord` model | `strix/core/proposals/models.py` — endpoint/param ref, agent CWE, C1–C8 answers, harnesses selected, per-harness `HarnessVerdict` (verdict + `evidence_class`), timing/cost, `InterventionFlags` matrix, append-only `add_verdict`/`attach_report`/`record_context` | implemented |
| 1.2 Additive funnel log on `report/state.py` | `strix/report/proposals.py` `FunnelLog` (append-only, in-memory index + JSON persist/load). `report/state.py` adds `self.funnel_log`, hydrates/saves `funnel.json`. Impact gate + `vulnerability_reports` semantics **unchanged** | implemented |
| 1.3 Pure derived metrics | `strix/report/proposals.py` — `compute_r_prop`, `compute_prec_gate`, `compute_r_e2e`, `compute_funnel_efficiency`; pure functions over the record list, external label set `V` supplied as a `set[str]` | implemented |

### Contract B — Proposal-Context Assembler (flag-gated recall layer)

| Task | Evidence | Status |
|---|---|---|
| 2.1 Control-Path verbaliser | `assembler.py::_verbalize_control_path` — P3 `reachability_seam` → one bounded line per layer (route / status / sink path); no full-graph dump; returns `None` when unknown | implemented |
| 2.2 Knowledge-Path priors | `assembler.py::_build_knowledge_path` + `_KNOWLEDGE_PRIORS` — per-class CWE prior keyed by the P3 `parameter_classifier` class | implemented |
| 2.3 C1–C8 checklist | `models.py::C1C8Checklist.default_questions` — fixed recall-oriented questions targeting FN-drivers (C3 delegation, C5 stateful, C6 concurrency, C7 trust-boundary); only answers vary | implemented |
| 2.4 Flag matrix + assembly entry | `assembler.py::assemble_proposal_context` — composes only enabled streams, records the active `InterventionFlags` into the returned `ProposalContext`. **Sets no `evidence_class`; writes no report state** | implemented |

### Contract C — Integration & Testing

| Task | Evidence | Status |
|---|---|---|
| 3.1 Wire into proposal-time tool path | `strix/tools/inventory/tools.py::propose_vulnerability_investigation`, registered in `strix/agents/factory.py::_BASE_TOOLS`. Reads ranked map, assembles context, appends to `funnel_log` via `start_proposal`, persists glass-box. Returns context to the agent; never runs a harness, never sets `evidence_class` | implemented |

---

## 2. Full gate (whole repo)

```bash
uv run ruff check . && uv run ruff format --check . && \
  uv run mypy strix/ && uv run pyright strix/ && \
  uv run bandit -r strix/ -c pyproject.toml && \
  uv run pytest tests/ -q
```

Result: **all green.**

- `ruff check .` — All checks passed
- `ruff format --check .` — 194 files already formatted
- `mypy strix/` — 0 errors (153 source files)
- `pyright strix/` — 0 errors, 0 warnings
- `bandit -r strix/ -c pyproject.toml` — 0 issues (High/Medium/Low/Undefined all 0)
- `pytest tests/ -q` — **334 passed, 4 skipped (Docker), 19 subtests passed** (was 328 before the §6a
  disposer→funnel wiring added 6 tests)
  - proposal subset: `tests/test_proposals_{funnel,assembler,integration,disposer_wiring}.py` — **19 passed**

---

## 3. Mandatory PBT invariants (the validation bar)

| Invariant | Test | What it asserts |
|---|---|---|
| **2.7 Assembler boundary (SAFETY-CRITICAL)** | `tests/test_proposals_assembler.py::test_no_report_state_mutation` | Assembled context sets no `evidence_class` and mutates no report state. *The validator must additionally TRACE the code path, not just rerun this test.* |
| **1.6 Funnel completeness** | `tests/test_proposals_funnel.py::test_completeness` (Hypothesis `@given`) | Every proposal reaching a harness carries ≥1 verdict with `evidence_class ∈ {diff,callback,reachability,race_result,none}` |
| **2.8 Ablation independence** | `tests/test_proposals_assembler.py::test_ablation_independence` | Toggling one flag changes only its contribution; other streams byte-identical |
| **2.9 Determinism** | `tests/test_proposals_assembler.py::test_stable_outputs` (Hypothesis `@given`) | Fixed reachability graph + param class → stable Control-Path / Knowledge output |

Tier-1 focused tests: funnel transition→record (1.4), four-metric computation (1.5), per-stream context
shape (2.5), active-flag recording (2.6), e2e flow records context + downstream verdict in the same
record (3.2), glass-box round-trip (3.3), and the no-report-state warning path.

---

## 4. Additivity / boundary self-audit (producer)

- **`evidence_class` is set in exactly one place** — `HarnessVerdict` (the disposer's output), constructed
  only by `FunnelLog.record_harness_verdict`. The assembler and the proposal tool never construct a
  `HarnessVerdict` and never write `vulnerability_reports`.
- **The proposal tool** (`propose_vulnerability_investigation`) only *reads* global report state and appends
  to `funnel_log`; with no global report state it returns the context plus a warning and records nothing.
- **`report/state.py` change is additive**: a new `funnel_log` field + `funnel.json` hydrate/save and a
  widened `set_global_report_state` signature (accepts `None`). The impact gate and `add_vulnerability_report`
  are untouched; pre-existing report/gate tests stay green.
- **Disposer untouched**: no changes to P2 diff / P3 OOB / P4 race paths.

---

## 5. Git / state management

- Working tree clean; `git diff --stat origin/propose-dispose..HEAD` is empty (in sync with remote).
- `.agents/` is gitignored (`.gitignore:88`); this report, tasks.md, manifest.yml, and memory_bank updates
  are **local-only** and were never `git add`-ed, per the engagement constraint.

---

## 6a. Disposer→funnel live wiring (added this session, pending push)

Resolves the producer observation that `FunnelLog.record_harness_verdict` had no production caller.
The wiring is **strictly additive instrumentation** — no harness/disposer logic, the impact gate, or
`vulnerability_reports` semantics changed.

- **Single seam:** `ReportState.add_vulnerability_report` (where every harness verdict converges) now calls
  the new `_link_disposer_verdict_to_funnel`, which records a `confirmed` `HarnessVerdict` (with the
  realized `evidence_class`) + links the `report_id` onto the matching `ProposalRecord`. Evidence-less
  (`"none"`) findings carry no harness verdict and are skipped.
- **Correlation:** explicit `proposal_id` (preferred), else a **conservative** best-effort single-match on
  endpoint via `_match_open_proposal` (links only an unambiguous, still-open proposal — never the wrong one).
- **No disposer edits:** P2 diff / P3 OOB / P4 race tool code is untouched; they inherit the link through the
  central report chokepoint. `evidence_class` is still set only by harnesses.
- **Glass-box thread-through:** optional `proposal_id` added to `create_vulnerability_report` + `_do_create`
  (`strix/tools/reporting/tool.py`) so the agent can pass the id it got from
  `propose_vulnerability_investigation`. Backward-compatible (defaults `None`).
- **Tests:** `tests/test_proposals_disposer_wiring.py` (6) — explicit-id link, best-effort match,
  `none`→no verdict, ambiguous→no-op, no-rematch of closed proposals, and additivity (no proposals ⇒ report
  byte-faithful, impact_gate_decision unchanged).
- **Gate after wiring:** ruff/format/mypy `strix/` (153 files)/pyright/bandit clean; **334 passed**, 4 skipped;
  the 33 report/gate/impact tests pass unchanged (additivity holds).

> Scope note for the validator: with this seam, only **confirmed** harness verdicts (those that reach a
> report) are recorded live. Recording **unconfirmed** harness runs in the live pipeline (e.g. an OOB
> candidate that never correlates) would require touching the harness tools and is intentionally deferred —
> it is out of "disposer unchanged" scope for Spec A. The funnel-completeness invariant (1.6) remains
> satisfied for proposals that reach a confirmed verdict.

## 6. Handoff

Spec A is implemented and gate-green. Flipping `propose-dispose-instrumentation` to `in_review`.
Requesting the distinct validator (`opus-4.8-pm-auditor`) to issue `verdict.md`:

1. **Trace** the locus-1 assembler boundary in code (PBT 2.7) — confirm no branch lets a proposal or
   assembled context set `evidence_class` or mutate report state.
2. Confirm the funnel is strictly additive — impact gate behaviour and existing report tests unperturbed.
3. Confirm completeness (1.6), ablation independence (2.8), determinism (2.9).

On a PASS verdict, dispatch Spec B `propose-dispose-validation` (research; currently `planned`).
