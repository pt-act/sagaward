# Propose–Dispose Instrumentation (Spec A) — Kickoff

> Feature **F-PD-A** · product-DAG **`unit`** · the buildable, keep-forever half of the propose–dispose program: a glass-box **funnel** (ProposalRecord + derived metrics) and a flag-gated **proposal-context assembler** (recall layer). The research half — B-V2P corpus, experiments, the quarantined self-confirm ablation, the paper — is the separate `propose-dispose-validation` spec (Spec B), dispatched after this lands.
> Source of truth: `.agents/specs/propose-dispose/specs/propose-dispose-instrumentation/{spec.md,tasks.md}` + `manifest.yml`.

> **SESSION 0 — RE-SYNC (read first if resuming OR if your context was compacted).** Your in-chat memory is not authoritative; the files on disk are. Re-load: `.agents/AGENTS.md` (Orion-OS v2.4.9 base — supersedes any local SOUL.md) → `.agents/AGENTS.project.md` → `.agents/memory_bank/active/current_focus.md` → this kickoff → the spec/tasks above → `.agents/PM/VALIDATION_PROTOCOL.md`. Then re-emit your §12 Session Manifest and continue from the resumption point in `current_focus.md`.

## Purpose — why this matters (read first)
This is the doctrine made *measurable*. The funnel turns the `proposal → harness → confirmation → report` pipeline from a black box into a glass box, and it is the substrate the propose–dispose paper reads its metrics off (`R_prop`, `Prec_gate`, `R_e2e`, `funnel_efficiency`). The assembler raises *proposal recall* so the agent reaches subtle vulns it would otherwise miss. **What "excellence" means here is one line: the assembler can raise recall but must never touch precision.** The agent proposes; the harness disposes. If any code path let the proposal layer set `evidence_class` or write report state, the proposer could self-confirm — the exact failure the whole engine (and the paper) exists to prevent. Build the instrumentation so that boundary is enforced in code, not by convention.

## Preconditions (verified)
- Depends on **Phase 0** (`report/state.py` impact gate) + **Phase 3** (`reachability_seam`, `parameter_classifier`) — both merged to `main`. **No Phase-5 dependency.** Startable now.
- Branch from current `main` (Phase 5 + dependency hardening already landed): `git checkout -b propose-dispose-instrumentation main`.

## STEP 0 — manifest (do first; local-only, never `git add` it)
- Confirm the `propose-dispose-instrumentation` entry exists with `status: planned` (added during the Phase-5 Step 0); flip it to `in_progress`, add `execution: {producer: kimi-k2p7-code, validator: opus-4.8-pm-auditor, arbiter: null}`, append a `spec_started` history event (append-only, chronological).

---

## DECISIONS / locked notes (read before coding)
1. **Additive only.** The funnel rides on existing `report/state.py`; **the impact gate and `vulnerability_reports` semantics do not change.** Existing report/impact-gate tests must stay byte-for-byte green. If you find yourself editing the gate, stop — you've left scope.
2. **The assembler is proposal-stage ONLY — the locus-1 boundary in code.** It sets **no `evidence_class`**, writes **no report state**, files **no `vulnerability_report`**, and never touches the disposer (P2 diff / P3 OOB / P4 race are unmodified). There must be **no code path** where assembled context or a proposal self-promotes. Only harnesses set `evidence_class`.
3. **The forbidden M4 self-confirm mode is NOT here.** The harness-disabled single-stage baseline lives in Spec B as research-only, build-time-gated, off-in-prod. Do not build or import it here.
4. **Reuse P0/P3 — never duplicate.** Funnel → `report/state.py`; Control-Path ← `core/inventory/parsers/reachability.py`; Knowledge priors keyed by `core/inventory/classify.py`; assembler plugs into the wired `tools/inventory` + `factory._BASE_TOOLS` path. Don't re-derive reachability or classification.
5. **Interventions target false-negative drivers (recall): C5/C6/C7.** C1/C2 are FP-drivers — credibility-safe, and only a *funnel-efficiency* cost, never a recall goal. Report Control-Path's C1 effect as efficiency, not recall.

---

## Contract A — Funnel / ProposalRecord · additive to `report/state.py` *(the measurement substrate)*
- `ProposalRecord`: endpoint/param ref, agent-declared vuln class (CWE), the C1–C8 self-check answers, harness(es) selected, **per-harness verdict + `evidence_class`**, timing/cost, and the **active-intervention flag matrix**.
- Append-only funnel log per proposal transition; **no change to the impact gate or `vulnerability_reports`**.
- Derived metrics as **pure functions** over the log: `R_prop`, `Prec_gate`, `R_e2e`, `funnel_efficiency` (labels `V` supplied externally where available).
- No credential/secret material in a record (inherit P1 redaction); records scope-bounded per engagement.

## Contract B — Proposal-Context Assembler · flag-gated recall layer
- Three **independently-ablatable** streams, each behind its own flag:
  - **Control-Path** — verbalize the P3 `reachability_seam` (route→handler→auth-mw→sink) into **compact, bounded** NL (multi-granularity; no full-graph dumps).
  - **Knowledge-Path** — per-endpoint-class CWE definitions/boundaries, keyed by the P3 `parameter_classifier` class.
  - **C1–C8 checklist** — fixed recall-oriented questions (concurrency C6, trust-boundary C7, delegated/implicit checks C3/C7); only the agent's *answers* vary.
- Assembly entry point composes **only enabled** streams and records the active flag matrix into the ProposalRecord. **Sets no `evidence_class`; writes no report state.**

## Contract C — Integration & Testing
- Wire the assembler into the proposal-time tool path (`tools/inventory` + `factory`), gated by the flag matrix; record the exact supplied context glass-box into the funnel.
- E2E: a proposal flows through the funnel with active interventions + supplied context recorded, and a downstream harness verdict's `evidence_class` lands in the **same** record.

---

## Validation discipline (the bar I will hold)
This spec is **not a precision-owning detector**, so there's no TP/TN detector burden — but it has four mandatory PBT invariants, and **one is safety-critical**:
- **Assembler boundary/purity (PBT 2.7) — the safety-critical one.** `∀ assembled context: sets no evidence_class ∧ writes no report state.` I will adversarially verify this by **tracing the code path**, not just re-running the test — confirming there is no branch by which the proposal layer can set `evidence_class` or mutate report state. This is the in-code locus-1 guarantee.
- **Funnel completeness (1.6):** every proposal that reached a harness carries ≥1 verdict with `evidence_class ∈ {diff,callback,reachability,none}`.
- **Ablation independence (2.8):** toggling one flag changes only its contribution; the others' output is byte-identical (clean E3 ablation).
- **Determinism (2.9):** fixed reachability graph + param class → stable Control-Path / Knowledge output.
- **Additivity check (mine):** I will confirm the existing `report/state.py` / impact-gate tests are unchanged in behavior and the full suite stays green — the funnel must not perturb the gate.

---

## Build order & gate
Critical path `TG1 funnel → TG2 assembler → TG3 integration+testing`; ~**2.5 iterations**, ~14 focused tests (lean by design — additive instrumentation, not a new primitive). **TG1 alone unblocks Spec B's M0/M1 metrics** — if schedule-pressed, land TG1 as its own deliverable first.
Gate per push: Tier-1 + the 4 PBT invariants + `ruff check` + `ruff format --check` + `mypy --strict` (changed) + `pyright` + `bandit -r strix/ -c pyproject.toml` + full `pytest tests/`, all green together. **Push per task group; verify `git diff --stat origin/<branch>` is empty before the completion report.** Update `current_focus.md` at every task-group boundary (resumption point + the active locked constraint) for compaction resilience.

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Propose–Dispose Instrumentation (Spec A, F-PD-A, product-DAG unit) per
.agents/specs/propose-dispose/specs/propose-dispose-instrumentation/{spec.md,tasks.md} and the locked
contracts in this kickoff. Deps Phase 0 + Phase 3 are complete; NO Phase-5 dependency.

START ON A FRESH BRANCH: git checkout -b propose-dispose-instrumentation main  (main has P0-P5 + dep
hardening). STEP 0: in manifest.yml (local, never git add), flip propose-dispose-instrumentation to
in_progress, add execution {producer, validator, arbiter:null}, append spec_started.

LOCKED DECISIONS:
1. ADDITIVE ONLY: the funnel rides on report/state.py; the impact gate and vulnerability_reports
   semantics DO NOT CHANGE. Existing report/gate tests must stay green. Editing the gate = out of scope.
2. The assembler is PROPOSAL-STAGE ONLY: it sets NO evidence_class, writes NO report state, files NO
   vulnerability_report, and never touches the disposer (P2/P3/P4 unchanged). No code path may let a
   proposal or assembled context self-confirm. Only harnesses set evidence_class.
3. The forbidden M4 self-confirm mode is NOT in this spec (it's research-only in Spec B). Don't build it.
4. REUSE, never duplicate: funnel -> report/state.py; Control-Path <- core/inventory/parsers/
   reachability.py; Knowledge priors keyed by core/inventory/classify.py; assembler plugs into
   tools/inventory + factory._BASE_TOOLS.
5. Interventions target FN-drivers (recall) C5/C6/C7. C1/C2 are FP-drivers -> efficiency cost only,
   never a recall goal.

Build in order: TG1 funnel/ProposalRecord (additive, append-only, pure derived metrics) -> TG2
assembler (3 flag-gated independently-ablatable streams; record the active flag matrix; set NO
evidence_class) -> TG3 wire into the proposal-time tool path + e2e.

MANDATORY PBT invariants (assert the SECURITY/structural meaning, not the implementation's behavior):
- assembler boundary: ∀ assembled context -> no evidence_class set, no report state written (the
  safety invariant; the validator will trace the code path, not just re-run this test);
- funnel completeness: ∀ proposal reaching a harness -> record carries >=1 verdict with evidence_class
  in {diff,callback,reachability,none};
- ablation independence: toggling one flag changes only its contribution, others byte-identical;
- determinism: fixed reachability graph + param class -> stable Control-Path / Knowledge output.
Also confirm the funnel is strictly additive: existing report/impact-gate tests unchanged.

GATE per push: ruff + ruff format --check + mypy --strict (changed) + pyright + bandit -r strix/ -c
pyproject.toml + full pytest tests/. Push per task group; verify git diff --stat origin/<branch> is
empty before the completion report. Update PROGRESS.md / current_focus.md at every task-group boundary
(resumption point + active locked constraint) for compaction resilience. Clean tree: explicit git add,
never -A; never git-add .agents/ or manifest.yml.

TG1 alone unblocks the research spec's metrics — if schedule-pressed, land TG1 first as its own
deliverable. When pushed with a completion report, the distinct validator issues verdict.md (it will
trace the assembler boundary in code + confirm the gate is unperturbed).
```
