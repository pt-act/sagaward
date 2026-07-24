# Propose–Dispose Validation — Planning / Requirements

> Conceptual grounding for the `propose-dispose-validation` research spec. Owned by PM/architect + author. Records *why* and the dependency/sequencing reasoning so it is not reconstructed in the implementation session.

## Canonical spec

**`spec.md` for this entry = the propose–dispose research proposal, v0.4** (`../paper/propose-dispose-research-proposal-v0.4.md`, author-owned). It already carries the equivalent of a full spec: thesis (Goal), falsifiable hypotheses (= requirements), method, experiments, threats-to-validity, M0–M5 plan, and paper framing. **It is more rigorous than a typical spec and must not be flattened.** This planning doc + `tasks.md` are the thin wrapper that places it in the manifest; the research content stays in v0.4.

> Status (2026-06-18): v0.4 is PM-signed-off and the author's cut has been **received and placed at `../paper/propose-dispose-research-proposal-v0.4.md`** (incorporating stats Changes 1–3, the H2a/H2b split with gap-stratified paired McNemar primary, the M0 seed re-rank, and the FP-arm headline reframe). The `spec.md` here remains the Spec-Architect wrapper that places v0.4 in the manifest; v0.4 is the canonical research narrative it references. The final paper is completed once everything is implemented and the empirical data is gathered.

## Hypotheses-as-requirements (the research analog of F-N)

| Hyp | What it requires the apparatus to measure | Hard part |
|---|---|---|
| H1 tradeoff break | sweep proposal-aggressiveness; `Prec_gate` flat as `R_prop` rises in propose–dispose, trades off in single-stage | watching `Prec_gate` for gate leakage — the single most important number |
| H2a (the win) | strix pipeline pairwise-correct > single-stage proxy, **margin widens as surface gap shrinks** | it is an *interaction* — report the main effect (McNemar) as robust primary, the small-gap-widening as the mechanism fingerprint |
| H2b (the honest limit) | proposer recall is gap-dependent → inherited E2E as false negatives | win-either-way: if recall is flat across the gap, frontier proposers don't inherit the trap at all — a bigger result |
| H3 / H3b | each proposal intervention lifts `R_prop` on its FN-target category; Control-Path's C1 effect is funnel-efficiency, not recall | decompose pairwise outcome into FP-arm / FN-arm contributions |
| H4 | cosmetic live-response perturbation leaves strix verdicts invariant; static proxy degrades | match dynamic range to avoid the floor-effect confound |

## Decisions already settled (do not re-open in implementation)

- **Headline claim:** "strix escapes the **false-positive arm** of gap-dictation; the false-negative arm is the proposer's recall problem (= H3 territory)." The flat "escapes gap-dictation" over-claims and is dropped (v0.4 / escalation A).
- **Harness can't be gap-dictated by construction** (it consumes behavior, not tokens) — so the test is aimed at the *pipeline* vs a single-stage proxy, not the harness in isolation.
- **E2 primary test = gap-stratified paired McNemar** (idiomatic; VulTriage Appendix C). Difference-of-correlations + bootstrap CIs are secondary/illustrative. No "prove-the-null" framing.
- **Corpus is small-gap-biased, not dozens-spanning** — McNemar-primary dissolves the corpus-size cost (the program's largest line item). Power-check the small-gap discordant count.
- **M0 seed = open-webui IDOR (CVE-2024-7041)**, conditional on verifying the fix is minimal-diff; **Flowise SSRF (CVE-2026-31829) = H1/OOB-callback showcase**, not the M0 discriminator. Confirm both CVE IDs resolve.
- **M4 single-stage ablation mode is research-only**, build-time/entrypoint gated, never a runtime toggle, with an off-in-prod regression test. It is the one piece of this spec that touches forbidden territory and is quarantined here, out of the product DAG.

## Dependencies

- **Hard (start-blocking), all COMPLETE:** Phase 0 (`impact_gate`), Phase 1 (`differential_engine`), Phase 2 (`inject_confirm_tool` / OOB), Phase 3 (`reachability_seam`, `parameter_classifier`), and the `propose-dispose-instrumentation` `unit` (funnel + assembler). → **startable now.**
- **Soft (consumption edges, gate only their experiments):** Phase 4 `race_harness_tool` → race B-V2P pairs + race experiments; Phase 5 `business_logic_orchestrator` → BL pairs + BL experiments. Encode as `consumes`, not `depends_on`, so the manifest shows the core H1/H2 work as unblocked.

## Why this is a separate `research` spec, not a phase

It *measures* the engine; it is not a capability the product needs to function, it consumes from multiple phases (cross-cutting, not the next link), and it contains the one component forbidden in production (M4). Its milestone (`propose-dispose-validated`) must **never gate a product milestone**. The buildable, keep-forever pieces (funnel + assembler) were split out into the `propose-dispose-instrumentation` `unit` precisely so they stay in the product DAG while this track does not.

## Explicit non-goals

- Not a product capability; does not block shipping.
- Does not build the funnel or assembler (that is the instrumentation `unit`); it consumes them.
- Does not modify the disposer or add evidence classes.
