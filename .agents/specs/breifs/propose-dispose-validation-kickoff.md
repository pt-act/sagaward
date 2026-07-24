# Propose–Dispose Validation (Spec B) — Kickoff

> Feature **F-PD-B** · `type: research` · **parallel track, NON-gating to product milestones.** The measurement + paper half of the program: B-V2P benchmark corpus, the quarantined single-stage self-confirm ablation (M4), experiments E1–E4, and the living preprint. It **consumes** the `propose-dispose-instrumentation` unit (Spec A, approved) — it builds neither funnel nor assembler.
> Source of truth: `.agents/specs/propose-dispose/specs/propose-dispose-validation/{spec.md,tasks.md}` + the canonical research narrative `propose-dispose-research-proposal-v0.4.md` + `manifest.yml`.

> **SESSION 0 — RE-SYNC (read first if resuming OR after a compaction).** Files on disk are authoritative, not chat memory. Re-load: `.agents/AGENTS.md` (v2.4.9) → `.agents/AGENTS.project.md` → `.agents/memory_bank/active/current_focus.md` → this kickoff → the spec/tasks + the v0.4 narrative → `.agents/PM/VALIDATION_PROTOCOL.md`. Re-emit your §12 Session Manifest, then resume from `current_focus.md`.

## Purpose — why this matters (read first)
This is where the doctrine is put on trial. The thesis: a **non-generative disposer** decouples recall (proposer) from precision (gate), breaking the precision/recall trap that single-stage and LLM-critic detectors are stuck on. You will measure that on **Behavioral-V2P pairs** — the same app at a vulnerable commit and its minimal-diff patch, deployed live — and let the *harness*, not the model, flip the verdict across the pair. **What "excellence" means here is the opposite of the usual coder reflex: the deliverable is the honest answer, not a positive one.** A detected false positive is a *good* sign (the over-proposing recall layer doing its job; the gate rejects it). An unflattering metric — `Prec_gate` leaking, recall flat across the gap, the proxy not degrading — is a *finding*, never something to massage. Writing optimistic results before the evidence lands is the Semantic Trap one level up. The paper's Results section stays **empty** until E1–E4 actually run. We impose on our own paper the same evidence gate the engine imposes on findings.

## Preconditions (verified)
- **Consumes** Spec A `propose-dispose-instrumentation` (approved @ `f4b9637`) — `funnel_log` + `proposal_context_assembler`. Hard deps: P1/P2 (IDOR/SSRF disposers). **Soft edges:** P4 `race_harness_tool` + P5 `business_logic_orchestrator` gate only the race / business-logic pairs and the full E-run — not the core H1/H2 work.
- **Non-gating:** `propose-dispose-validated` must never gate a product milestone.
- Branch from current `main` (or rebased onto Spec A once it merges).

## STEP 0 — manifest + the funnel-completeness prerequisite
- **Manifest (local-only):** flip `propose-dispose-validation` to `in_progress`, add `execution: {producer: <real model id>, validator: opus-4.8-pm-auditor, arbiter: null}`, append `spec_started`.
- **PREREQUISITE — complete the funnel (carried from the Spec A verdict, recommended path (a)).** Spec A's funnel records **confirmed runs only**; Spec B's metrics need **all** harness runs (`funnel_efficiency = harness_runs/|C|`, `Prec_gate = |C∩V|/|C|`). Add a **minimal additive emit-hook** to the harness tools that records *every* harness run (confirmed or unconfirmed) into the funnel — **emit-only: it must not change what the harness confirms or any `evidence_class` it assigns.** Prove it with a behavior-identical test (harness verdicts + evidence_class byte-identical with and without the hook). This preserves gate-neutrality in substance (the disposer's *disposition* is unchanged; only observability is added) while making `Prec_gate`/`funnel_efficiency` unbiased. Do this before E1–E4, or the headline metrics are biased.

---

## DECISIONS / locked notes (read before coding)
1. **This is a RESEARCH spec — the validation model is different.** Hypotheses (H1–H4) are the requirements; experiments (E1–E4) are the deliverables. **Only the *software* this spec adds carries hard software gates** — the M4 ablation mode's off-in-prod guardrail and gate-neutrality (PBT). Everything else is validated under the **research-validity gate**: pre-registration, recall-over-known-labels, no-imported-magnitudes. Do not PBT-gate an experiment; do not treat a hypothesis decision as a passing test.
2. **M4 single-stage ablation is the ONE forbidden-path piece — quarantine it.** The harness-disabled baseline (agent self-confirms) is **build-time / entrypoint gated, NEVER a runtime toggle**, and must ship with an **off-in-prod regression test** (`∀ production config: single_stage_ablation_mode = OFF ∧ no production entrypoint reaches the self-confirm path`). This never enters the product DAG. The validator will trace this guardrail in code, hardest of all.
3. **Gate neutrality (architecture invariant): `C ⊆ P`.** The gate only *removes* proposals, never adds findings; the disposer's disposition is never modified. The Step-0 emit-hook is observability-only and must be proven behavior-identical.
4. **Consume Spec A — never rebuild.** `funnel_log` + assembler are imported, not re-implemented. `report/state.py` (the `Prec_gate` source) stays unmodified beyond the additive emit-hook.
5. **Pre-register before you peek.** E2's gap metric, primary test, and equivalence margin δ are registered **before any outcome is observed** (anti-p-hacking). Recall is reported as *recall-over-known-labels* with the unknown-unknown caveat — never absolute. The single-stage baseline is **self-measured**; cited papers establish the trap's *shape*, not its coordinates.
6. **Honest framing is the deliverable.** Empty Results until E1–E4 run. Tag every claim `architectural / prior-work / under-test / pending-evidence`. An unflattering result is publishable.

---

## Contract A — M0 walking skeleton + seed + funnel completion
- The Step-0 emit-hook (above). M0 readout per pair: *did the harness flip vuln→fixed while the raw proposal did not?*
- Seed targets, deployed live in the sandbox (`runtime/docker_client.py` lifecycle): **open-webui IDOR** (CVE-2024-7041, `/api/v1/memories/{id}/update`) via a **synthesized minimal one-line ownership-check patch**; **Flowise SSRF** (CVE-2026-31829, ≤3.0.12 → 3.0.13) for the H1/OOB showcase.
- Cross-check the four funnel metrics off a synthetic funnel against the M0 hand-computation.

## Contract B — B-V2P benchmark corpus (F-1)
- Dockerized {vuln-commit, patch-commit} pairs; each ships ground-truth `V`; **minimal-diff** (single security-logic change, curated or synthesized); **small-gap-biased** (the McNemar-primary design needs discordant small-gap pairs, not breadth). ≥1 per primitive: IDOR/BFLA (P1/P2), SSRF/XXE (P3) now; race (P4) + business-logic (P5) soft-edged. **Reuse the Phase-5 `benchmarks/business_logic_fixture` vuln/patch as the first business-logic pair** — it was built for this. Power-check the small-gap discordant count.

## Contract C — M4 single-stage ablation mode (the safety-critical software)
- Harness-disabled baseline (agent self-confirms) + optional static-proxy (LLM-critic) baseline; **build-time/entrypoint gated, off-in-prod test mandatory**; dynamic range matched to the pipeline to avoid a floor-effect confound. This is the only shippable software in the spec and it carries the hard PBT gate (invariants 1 + 2).

## Contract D — Experiments E1–E4 + paper (research deliverables)
- **E1 (H1):** sweep proposal aggressiveness, both modes; single-stage shows recall↑/precision↓; propose–dispose shows `R_e2e`↑ with **`Prec_gate` ≈ constant** (gate leakage `Prec_gate<1` is the primary watch). 
- **E2 (H2a/H2b):** **gap-stratified paired McNemar (one-sided)** primary — strix pairwise-correct > single-stage; decompose each pair into FP-arm (patched) / FN-arm (vuln) so H2a/H2b can't confound. Difference-of-correlations + bootstrap CIs illustrative only; underpowered interaction reported as such.
- **E3 (H3/H3b):** full vs −Control vs −Knowledge vs −Checklist; readouts: `R_prop` overall + per FN-category, and `funnel_efficiency` with C1-attributed FP-proposal rate.
- **E4 (H4):** semantic-preserving perturbations leave strix verdicts invariant; the static proxy degrades.
- Paper draft consolidates per pre-registered tests; Claims Ledger tags every statement.

---

## Validation discipline (the bar I will hold)
- **HARD software gates (PBT, I trace these in code):** (1) **M4 production-off** — no production entrypoint reaches the self-confirm path; (2) **gate neutrality** `C ⊆ P` + the emit-hook is behavior-identical; (3) **funnel completeness** now including unconfirmed runs (post Step-0 hook); (4) **no third-party leak** (OOB via the self-hosted P3 oracle; no target data leaves the sandbox).
- **Research-validity gates (RV):** **pre-registration** of E2's metric/test/δ before outcomes; **recall-over-known** with the unknown-unknown caveat; **no-imported-magnitudes** (baseline self-measured).
- I will **not** approve an experiment as if it were a passing test — research deliverables are judged on method validity, not green/red. The M4 guardrail and gate-neutrality are the only things I gate like code.

## Build order
M0 (skeleton + seed + Step-0 funnel completion) → M2 (corpus) → M4 (ablation + off-in-prod guardrail) → M5 (E1–E4 + paper). Race/business-logic pairs and their experiments are **soft-edged** behind P4/P5 — they don't block the core H1/H2 IDOR/SSRF work. Gate per software push: ruff + ruff format --check + mypy --strict (changed) + pyright + bandit -r strix/ -c pyproject.toml + full pytest tests/. Push per milestone; verify origin; update `current_focus.md` at every boundary (resumption + active constraint) for compaction resilience.

---

## Spec-A close-out follow-ups (small; do alongside M0)
From the Spec A verdict — none blocking, fold in opportunistically:
1. **Strengthen the assembler boundary test** (`test_no_report_state_mutation`) to assert the *structural* fact (`"evidence_class" not in ProposalContext.model_fields`; the proposal-stage call graph contains no `record_harness_verdict`/`add_vulnerability_report`) rather than a `ReportState` the assembler never receives.
2. **Update the evidence-set spec text** from the 4-way to the implemented 5-way `{diff, callback, reachability, race_result, none}`.
3. **Record the real producer** in the manifest `execution.producer` (Opus instance), not the stale `claude-kimi-k2p7-code` harness label.

---

## Coder kickoff prompt (relay to the producer)

```text
Ground Propose–Dispose Validation (Spec B, F-PD-B, type: research, NON-gating) per
.agents/specs/propose-dispose/specs/propose-dispose-validation/{spec.md,tasks.md} + the v0.4 narrative
+ the locked contracts here. CONSUME Spec A's funnel + assembler; build neither.

START on a fresh branch from main. STEP 0 (manifest local-only): flip propose-dispose-validation to
in_progress, add execution block, append spec_started. THEN the funnel-completeness prerequisite: add a
MINIMAL ADDITIVE emit-hook to the harness tools so EVERY harness run (confirmed or unconfirmed) lands in
the funnel — emit-only, must NOT change what the harness confirms or any evidence_class; prove it with a
behavior-identical test. (Spec A's funnel is confirmed-only; the metrics need all runs.)

LOCKED DECISIONS:
1. RESEARCH spec — different validation model. Hypotheses H1-H4 = requirements; experiments E1-E4 =
   deliverables. ONLY the software you add (M4 ablation guardrail + gate-neutrality) gets HARD software
   gates (PBT). Everything else is judged under the research-validity gate: pre-registration,
   recall-over-known, no-imported-magnitudes. Do not PBT an experiment; do not treat a hypothesis
   decision as a passing test.
2. M4 single-stage self-confirm ablation is the ONE forbidden-path piece: build-time/entrypoint gated,
   NEVER a runtime toggle, with an off-in-prod regression test. It never enters the product DAG.
3. Gate neutrality C ⊆ P: the gate only removes proposals; the disposer's disposition is never modified
   (the emit-hook is observability-only, proven behavior-identical).
4. Consume Spec A's funnel/assembler; report/state.py unmodified beyond the additive emit-hook.
5. PRE-REGISTER E2's gap metric, primary test, and δ BEFORE observing outcomes. Recall = recall-over-known
   with the unknown-unknown caveat. Single-stage baseline is self-measured.
6. Honest framing IS the deliverable: empty Results until E1-E4 run; a detected FP is a good sign; an
   unflattering metric is a finding, not something to bury. Tag every claim in the Claims Ledger.

Build order: M0 (skeleton + seed targets open-webui IDOR CVE-2024-7041 + Flowise SSRF CVE-2026-31829,
deployed live in the sandbox + funnel completion) -> M2 (B-V2P corpus: dockerized minimal-diff vuln/patch
pairs, ground-truth V, small-gap-biased, >=1 per primitive; reuse the Phase-5 business_logic_fixture as
the first BL pair) -> M4 (ablation mode + off-in-prod guardrail) -> M5 (E1-E4 + paper draft). Race/BL
pairs soft-edged behind P4/P5 — don't let them block the core H1/H2 IDOR/SSRF work.

GATE per software push: ruff + ruff format --check + mypy --strict (changed) + pyright + bandit -r
strix/ -c pyproject.toml + full pytest tests/. The M4 production-off guardrail + gate-neutrality + the
emit-hook behavior-identical test must be green. Push per milestone; verify git diff --stat
origin/<branch> empty before any completion claim; update current_focus.md at every boundary. Clean
tree: explicit git add, never -A; never git-add .agents/ or manifest.yml.

When M4's guardrail software lands, signal for validation — the distinct validator traces the
off-in-prod path in code + gate-neutrality, and reviews the research deliverables on method validity
(pre-registration, recall-over-known, no-imported-magnitudes), not green/red.
```
