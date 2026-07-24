# Propose–Dispose: Decoupling Recall and Precision in Evidence-Gated Vulnerability Discovery

**Canonical `spec.md` for `propose-dispose-validation`** (`type: research`, non-gating to product milestones)
Status: **v0.4** · Date: 2026-06-15 · Owner: strix program (PM/architect + author)

> **Program placement.** This document is the research spec. The buildable, product-reusable half — the funnel/`ProposalRecord` (M1) and the proposal-context assembler (M3) — lives in the separate `propose-dispose-instrumentation` (`type: unit`, in the product DAG). **This spec consumes those; it does not build them.** The one component that touches the forbidden locus-1 path — the M4 single-stage ablation mode — is **quarantined here** and never enters the product capability graph. Hard (start-blocking) deps P0–P3 + the instrumentation unit are complete → startable now; Phase 4 (`race_harness_tool`) and Phase 5 (`business_logic_orchestrator`) are **soft edges** gating only the race / business-logic experiments.
>
> **Changelog v0.3 → v0.4:** stats Changes 1–3 (prove-the-null → difference-of-correlations + bootstrap CIs + power-gated TOST + pre-registration); **H2 split into H2a/H2b** with **gap-stratified paired McNemar as the primary E2 test** (correlation demoted to illustrative); main-effect-primary / interaction-as-fingerprint; per-pair **FP-arm/FN-arm decomposition**; small-gap-biased corpus + discordant-count power check; **Change 4 moved to M0 seed selection**; **headline reframe** to the false-positive-arm claim; M0 seed verified and switched to a synthesized minimal patch.

---

## 0. One-paragraph thesis

The vulnerability-detection literature treats LLM vulnerability judgment as a single binary decision and runs into a precision/recall trap: classifiers tuned for recall hallucinate vulnerabilities on patched code (catastrophic FPR), while classifiers tuned with explicit reasoning suppress false alarms only by missing real bugs (low recall). Strix's *agent-proposes / harness-disposes* architecture **factorizes** the decision into a high-recall **proposal** stage (the LLM agent) and a high-precision **confirmation** stage (deterministic, evidence-gated harnesses). Because the two stages are owned by independent components, proposal recall can be pushed aggressively without degrading confirmation precision. The honest, defensible form of the claim: **strix escapes the false-positive arm of gap-dictation** (it will not flag a patched app as vulnerable, because no evidence fires), **while the false-negative arm — a subtle bug the proposer never proposes — is inherited by the proposal layer and is the program's true recall ceiling.** We propose an instrumentation layer (built in the instrumentation unit), a behavioral benchmark, and a set of falsifiable experiments to validate or refute this on real targets.

---

## 1. Background: the trap is single-stage

Two recent papers, found *after* the strix specs were written and independently converging on its core constraint:

- **Semantic Trap** (Huang et al., arXiv 2601.22655). Fine-tuned LLM detectors pattern-match rather than reason. Three measured symptoms: (i) pairing-sensitive performance — strong on *vuln vs. unrelated* (V2N), collapsing on *vuln vs. its own patch* (V2P); (ii) gap-dictated decisions — accuracy tracks the CodeBLEU textual gap (|ρ|<0.1 but systematic, p<0.05), not the security logic; (iii) fragility to semantic-preserving perturbation. Critically: **without-CoT → high recall + catastrophic FPR; with-CoT → lower FPR + low recall.** A single-axis tradeoff. Failure taxonomy C1–C8: C1 (control-flow) + C2 (API hallucination) drive **false positives**; C5 (CWE misapplication) + C6 (concurrency) drive **false negatives**; C5 is most frequent overall.
- **VulTriage** (Tang et al., arXiv 2605.09461). Triple-path context augmentation — Control (AST/CFG/DFG → NL), Knowledge (CWE RAG), Semantic (LLM self-summary) — raises pair discrimination and cuts FPR, but even SOTA tops out at ≈0.64 acc / 0.69 F1 on hard pairs. Augmentation helps; it does not make a single-stage classifier reliable.

**Key observation.** Both papers improve the *quality of one binary decision*. Neither separates "what to investigate" from "what is confirmed true." That separation is exactly strix's architecture.

**Closest prior art — and the one axis we differ on.** The factorization itself is *not* new. A line of multi-agent LLM systems already separates *proposing* a candidate from *judging* it: GPTLens (Hu et al., in VulTriage Table 1) pairs an auditor agent that proposes candidate vulnerabilities with a critic agent that scores them; VulTrial (Widyasari et al., ICSE 2026) runs a four-role courtroom to a verdict by multi-round debate; ConColl (Tsai et al., EMNLP 2025) cascades single → RAG → multi-agent stages gated by model-reported confidence. All three decouple proposal from disposition, and all three remain trapped — on the PrimeVul hard-pair set they sit at ≈0.51–0.54 accuracy (GPTLens 0.518, VulTrial 0.536, ConColl 0.513), barely above the 0.50 floor, with VulTriage's augmentation reaching only 0.636. In every one of these systems **the disposer is itself a language model judging the same artifact the proposer judged**, so precision remains owned by a model reading code. Their low pair-accuracy establishes that the trap *survives the agent split*; our explanatory claim — that precision and recall stay coupled because the disposer re-judges the same artifact, so proposal aggressiveness leaks into the final verdict — is precisely what **H1 puts under test**, not a result we import from them.

Propose–dispose differs on this single axis: the disposer is **not a model and does not re-read the code.** It is a deterministic, evidence-producing harness that *observes runtime behavior* — an OOB callback correlated to a minted token, a differential across authenticated identities, a race interleaving, a reachability path. Confirmation requires `evidence_class ≠ none`: an artifact a model cannot fabricate by reasoning harder. Because precision is owned by the harness rather than a second LLM, raising `R_prop` cannot leak into `Prec_gate` — the property the LLM-critic systems lack. The one-sentence novelty: **we replace the LLM critic with a deterministic behavioral oracle.** (See the positioning ladder in §9.)

---

## 2. The factorization and why it breaks the trade

Define, for a target with ground-truth-labeled vulnerability set `V`:

- Proposals `P` — candidates the agent emits for investigation.
- Confirmations `C ⊆ P` — proposals the harness backs with `evidence_class ≠ none`.
- **Proposal recall**: `R_prop = |P ∩ V| / |V|`
- **Confirmation precision (gate leakage)**: `Prec_gate = |C ∩ V| / |C|` (≈ 1 by design; we *measure* leakage)
- **End-to-end recall**: `R_e2e = |C ∩ V| / |V| = R_prop · (|C ∩ V| / |P ∩ V|)`

The decisive structural fact:

> In a single-stage detector, raising recall lowers precision (the trap).
> In propose–dispose, `Prec_gate` is owned by the **harness**, not the proposer. Raising `R_prop` cannot lower `Prec_gate` — different component. The only cost of over-proposing is **compute** (more harness runs), not **credibility** (false reports).

**Load-bearing corollary (the gate is neutral).** `C ⊆ P`: the gate can only *remove* proposals, never *add* findings. Therefore the gate cannot rescue a vulnerability the proposer never proposed. Any gap-dictation that lives in the proposer — failing to propose a subtle vuln because it *looks* benign (small surface gap) — is **inherited end-to-end as a false negative**. This is why the architecture escapes the *false-positive* arm of gap-dictation (the gate refuses to confirm patched code) but **not** the *false-negative* arm (the proposer's recall). Gap-dictation is not eliminated; it is **relocated to the recall side**, where it coincides with the C5/C6 false-negative regime and with H3.

So the optimization splits cleanly:
- Maximize `R_prop` (drive the proposal layer to over-propose; attack C5/C6 false-negative modes).
- Keep `Prec_gate ≈ 1` (the deterministic gate already does this).
- Track `funnel efficiency = harness_runs / |C|` as the honest price of the doctrine.

**This is the contribution.** Everything below is the apparatus to prove or disprove it.

---

## 3. Hypotheses (falsifiable)

| # | Hypothesis | Falsifier |
|---|---|---|
| **H1 — tradeoff break** | As proposal aggressiveness increases, *single-stage* mode shows recall↑ / precision↓ (reproduces the trap); *propose–dispose* mode shows `R_e2e`↑ while `Prec_gate` stays ≈ constant. | `Prec_gate` falls materially as `R_prop` rises (gate leaks under over-proposal). |
| **H2a — the win (FP-arm)** | **Main effect (primary):** on B-V2P pairs, the strix pipeline's per-pair verdict correctness exceeds a single-stage/CoT proxy's (gap-stratified paired McNemar, one-sided). **Mechanism fingerprint (secondary, power permitting):** the margin *widens as the surface gap shrinks*. | strix is not significantly more pairwise-correct than the proxy on the main effect. *(The interaction failing to reach significance is reported as underpowered, not as a falsification of H2a.)* |
| **H2b — the honest limit (FN-arm)** | The proposer's proposal-recall is itself gap-dependent — it drops on small-gap pairs — and because the gate is neutral this is inherited end-to-end as false negatives. | Proposal-recall is flat across the gap (the proposer does not inherit the trap at all) — a stronger, more publishable result. |
| **H3 — proposal interventions lift recall on FN-target categories** | Knowledge-Path raises `R_prop` on **C5**-attributed misses; the C-checklist on **C6/C7**; Control-Path on **C3** (reachability/context). Single-intervention ablation, recall-over-known-labels per category. | An intervention shows no significant `R_prop` gain on its FN-targeted category. |
| **H3b — Control-Path's precision effect is funnel-efficiency, not recall** | Adding Control-Path lowers **C1**-attributed false-positive *proposals*, reducing `harness_runs / \|C\|` without materially changing `R_prop`. | Control-Path's only measurable effect is on `R_prop`, with no funnel-efficiency improvement. |
| **H4 — perturbation invariance** | Cosmetic perturbation of the live target (header reorder, error-text reword, latency jitter, response whitespace) leaves strix verdicts invariant; a static-proxy classifier degrades. | strix verdict variance under perturbation ≈ static proxy's. |

---

## 4. Method

### 4.1 Funnel instrumentation (consumed from the instrumentation unit)

The funnel / `ProposalRecord` is **built in `propose-dispose-instrumentation` (TG1)**, additive to `report/state.py`. This spec **consumes** it: each record captures endpoint/param ref, agent-declared vuln class (CWE), the C1–C8 self-check answers, the harness(es) selected, every harness verdict + `evidence_class`, and timing/cost — the substrate for `R_prop`, `Prec_gate`, `R_e2e`, and `funnel_efficiency`. No gate change.

### 4.2 Behavioral-V2P (B-V2P) — the benchmark

Static V2P pairs a vulnerable function with its patch. **B-V2P pairs a *deployed* vulnerable app with its *patched* deployment** — the same application straddling a security fix, each containerized and run live in the strix sandbox. The experiment asks whether the *harness* (not the model) flips its verdict across the pair.

- **Construction**: prefer real CVE fix commits; **where a clean minimal-diff fix is not publicly available, synthesize a minimal patch** (a single security-logic change) — this is *preferred* for the discriminating pairs because it controls the surface gap to a minimum (see §8, M0).
- **Bias the corpus toward small-gap pairs**, not a dozens-spanning range: the primary test (gap-stratified McNemar, §5) needs **discordant** pairs in the small-gap stratum, not breadth. Power-check the discordant count before claiming the interaction.
- **Coverage**: ≥1 pair per primitive — P1/P2 (IDOR, BFLA), P3 (SSRF, blind XXE) now; race (P4) and business-logic (P5) as those phases land (soft edges).
- **Labels**: each pair ships ground-truth `V`; report recall as *recall-over-known-labels* with the unknown-unknown caveat.
- **Deployment harness**: reuses `strix/runtime/docker_client.py` lifecycle.

### 4.3 Proposal-recall interventions (assembler consumed from the instrumentation unit; ablation run here)

The flag-gated assembler is **built in `propose-dispose-instrumentation` (TG2)**. This spec runs its **ablation (E3)**. Interventions raise **recall**, so they target the Semantic Trap's **false-negative drivers** (C5 + C6, FN side of C3/C7) — *not* its false-positive drivers (C1 + C2):

| Intervention | Targets | Failure direction | Effect in propose–dispose |
|---|---|---|---|
| **Knowledge-Path priors** (per-class CWE definitions/boundaries at proposal time) | **C5** (most frequent FN-driver) | False negative | **Raises `R_prop`** |
| **C1–C8 self-interrogation checklist** | **C6** (concurrency), **C7** (trust-boundary, FN side) | False negative | **Raises `R_prop`** |
| **Control-Path context** (verbalized route→handler→auth-mw→sink, the P3 reachability seam) | **C3** (scope/context isolation) | FN side of C3 | **Raises `R_prop`** via reachability/context |
| *(same intervention, second-order)* | **C1** (control-flow misread — *FP-driver*) | False positive | **Funnel-efficiency gain**, not recall |

**FP-drivers are a cost line, never a credibility line.** Both C1 and C2 are credibility-safe — neither can produce a false *finding* — and both carry only a residual funnel-efficiency cost (C1 reducible at the proposal stage by Control-Path; C2, API/behavior hallucination, reducible only *after* a harness attempt, disposed by the **class-appropriate** harness: P3 OOB for callback-observable SSRF/XXE/blind, P2 differential for authz, race harness for TOCTOU, else stays unconfirmed). **FN-drivers (C5/C6/C7) are the proposal-recall targets.** Precision lives in the harness; recall lives in the proposer.

### 4.4 Disposers — unchanged

The deterministic harnesses (P2 differential, P3 OOB correlation, P4 reachability, Phase-4 race) are the precision-owning stage and are **not** modified. Their `evidence_class` outputs feed `Prec_gate` directly.

---

## 5. Experiments

| Exp | Tests | Design |
|---|---|---|
| **E1 — tradeoff curve (H1)** | The core claim | Sweep a proposal-aggressiveness knob (checklist threshold). Plot recall vs. precision for (a) single-stage agent-as-judge mode and (b) full propose–dispose. Expect a tradeoff curve for (a), a flat-precision recall gain for (b). **Watch `Prec_gate` — the single most important number.** |
| **E2 — gap-dictation (H2a/H2b)** | Behavioral grounding | Compute a surface-gap metric per pair (response-diff size; CodeBLEU on handler source where white-box). **Primary test:** gap-stratified **paired McNemar** of the strix pipeline vs a single-stage proxy on the same pairs (main effect = H2a). **Secondary/illustrative:** difference-of-correlations (Fisher-z / paired bootstrap) and per-arm Spearman vs. gap, with **bootstrap 95% CIs**; report effect size + CI, not just p. **Decompose each pair into FP-arm (patched side) and FN-arm (vuln side) contributions** so H2a (FP-win) and H2b (FN-loss = proposer recall) cannot confound. The small-gap-widening interaction is the **mechanism fingerprint**, reported directionally, power permitting. Optional TOST for `ρ_strix` within `±δ` only if powered. **Pre-register** the gap metric, the test, and `δ` before looking at outcomes. |
| **E3 — intervention ablation (H3, H3b)** | Proposal interventions | Full vs. −Control vs. −Knowledge vs. −Checklist. **Two readouts per condition:** (a) `R_prop` overall and per targeted FN-category (C5/Knowledge, C6-C7/Checklist, C3/Control) — H3; (b) `funnel_efficiency = harness_runs/|C|` with the C1-attributed FP-proposal rate broken out — H3b. Expected: Knowledge/checklist move `R_prop` on their categories; Control-Path moves both `R_prop` (via C3) and funnel efficiency (via C1). If Control-Path moves only one, the source's FP/FN split does not transfer to the agentic regime — itself publishable. |
| **E4 — perturbation invariance (H4)** | Robustness | Apply semantic-preserving perturbations to the *live target's responses*; measure verdict variance for strix vs. static proxy. |

A **single-stage ablation mode** is required for E1/E2/E4 baselines (see M4 safety guardrail in §7). Design it to avoid the floor-effect confound the Semantic Trap authors flag (match dynamic range when comparing).

---

## 6. Threats to validity

- **Recall denominator completeness.** `V` is known-labels only; report recall-over-known and never claim absolute recall.
- **B-V2P minimal-diff fidelity.** Real fix commits bundle changes; curate or synthesize minimal patches so verdict flips are attributable to the security delta. (Realized at M0 — see §8.)
- **Over-proposal compute cost.** The doctrine's price is harness runs. Report `funnel_efficiency` as a first-class result.
- **Gate leakage is the real risk.** If aggressive proposals get *spuriously* confirmed, `Prec_gate < 1` and the thesis weakens. E1 watches this directly; it is the most important number in the study.
- **Single-stage fairness / floor effects.** Construct the baseline so the comparison is honest; the Semantic Trap CoT "escape" may be a floor effect — do not commit the symmetric error in reverse.
- **The cited magnitudes establish the trap's *shape*, not its coordinates.** Both papers measure fine-tuned 7–8B classifiers over static C/C++ pairs. Keep the E1/M4 single-stage baseline **self-measured**; never imply the papers' numbers transfer. The C1–C8 taxonomy is itself an LLM-as-judge artifact (Semantic Trap §IV-D), so read "targets C5" as "targets the C5-*described* failure mode."
- **Correlation power and corpus size.** A per-pair gap-correlation needs far more than a handful of pairs; at small n the Spearman CI spans most of [−1, 1]. This is why the **primary** test is the paired McNemar (which needs *discordant* small-gap pairs, not breadth) and the correlation is illustrative with explicit wide CIs. **Power-check the small-gap discordant count**; do not report a tight ρ from a tiny n. Concentrate the corpus in the small-gap stratum.

---

## 7. Implementation plan (milestones; threaded through the program)

| Milestone | What | Where it lives |
|---|---|---|
| **M0 — walking skeleton** | One small-gap B-V2P pair; run strix both modes; capture the funnel; read the single number (§8). | this spec (TG0) |
| **M1 — funnel** | `ProposalRecord` + funnel log; metrics `R_prop`/`Prec_gate`/`R_e2e`/`funnel_efficiency`. | **instrumentation unit** (consumed here) |
| **M2 — B-V2P corpus** | small-gap-biased, labeled, dockerized, minimal-diff pairs; ≥1 per primitive. | this spec (TG2) |
| **M3 — proposal-context assembler** | Control-Path + Knowledge priors + C-checklist, flag-gated. | **instrumentation unit** (ablation run here, TG3) |
| **M4 — single-stage ablation mode** | harness-disabled baseline + static-proxy (+ optional LLM-critic) baseline. | this spec (TG4) — **quarantined** |
| **M5 — experiments + write-up** | E1–E4 + paper. | this spec (TG5) |

> **M4 safety guardrail (must-hold).** The ablation mode disables the harness and lets the agent self-confirm — exactly the locus-1 failure `AGENTS.project.md` forbids. It is **research apparatus only**: hard-gated via a separate entrypoint or build-time flag, **never a runtime config toggleable mid-scan**, with a regression test asserting it is **off** in the production configuration. This is why M4 lives in this research spec and never enters the product DAG. The same guardrail binds any harness-disabled baseline.

**Seed assignment (verified 2026-06-15):** M0 discriminating seed = **open-webui IDOR (CVE-2024-7041)** via a **synthesized minimal patch** (the public record has no clean single-commit fix — only the vulnerable file/line `memories.py` and the huntr bounty resolve; both CVE IDs confirmed real). **Flowise SSRF (CVE-2026-31829, ≤3.0.12 → 3.0.13)** = the **H1 / OOB-callback showcase pair**, not the discriminator. Soft edges: P4 race + P5 business-logic pairs/experiments are deferred behind their phases.

---

## 8. Minimal first experiment (M0 — actionable now)

1. Take **open-webui** at a fixed commit (the `/api/v1/memories/{id}/update` handler in `memories.py`, where a low-priv identity can edit another user's memory).
2. **Build the pair by synthesized minimal patch:** the `fixed` deployment adds the **one-line ownership check** (`memory.user_id == current_user.id`); the `vuln` deployment is that exact commit with the check removed. This guarantees a security-only, minimal surface gap — the strongest discriminating condition (a large-diff pair lets even a naive agent flip, and the result is uninformative). Containerize both.
3. Run current strix against each; capture the funnel (proposals, harness runs, `evidence_class` per finding).
4. Compute by hand: `R_prop`, `Prec_gate`, the verdict-flip across the pair, and the surface gap.
5. **Read the single number that matters first:** did the **P2 differential harness** flip vuln→fixed (cross-identity write succeeds on `vuln`, blocked on `fixed`) **while the agent's *raw proposal* did not**? On this small-gap pair that is the first H2a data point. If the raw proposal already flips cleanly and reliably, the gate is doing less than assumed — equally important to learn early.

*(Flowise SSRF is the parallel H1 showcase: on `vuln`, the OOB oracle mints a token, the callback fires → `evidence_class=callback`, confirmed; on `fixed` (3.0.13), no callback → unconfirmed. The unforgeable callback is the cleanest demonstration of the factorization, distinct from the small-gap discrimination M0 tests.)*

---

## 9. Paper framing

- **Title (working):** *Propose–Dispose: Breaking the Precision/Recall Trap in LLM Vulnerability Discovery with Evidence-Gated Behavioral Confirmation.*
- **Headline claim (reframed, honest):** **strix escapes the false-positive arm of gap-dictation; the false-negative arm is the proposer's recall problem.** The flat "escapes gap-dictation" over-claims — the gate is neutral, so the proposer's gap-dictation is inherited as recall loss. This unifies H2 with H3 and is more defensible and more publishable than the flat claim.
- **Positioning ladder (four rungs of prior art + strix):**

  | Rung | Representative | Unit of analysis | Disposer | Trap broken? |
  |---|---|---|---|---|
  | Raw tokens | PrimeVul prompting | static source | model | No |
  | + static structure | VulTriage (Tang et al.) | static AST/CFG/DFG | model | No (0.64 acc ceiling) |
  | + distilled reasoning / CoT | Semantic Trap (Huang et al.) | static source + CoT | model (self) | No (floor-effect "escape") |
  | + multi-agent factorization | GPTLens / VulTrial / ConColl | static source | **another LLM** | No (≈0.51–0.54 acc) |
  | + observed runtime behavior w/ evidence | **strix (propose–dispose)** | **running deployment** | **deterministic harness** | **claim under test (H1)** |

  The fourth rung is load-bearing: without it a reviewer asks "isn't this GPTLens with extra steps?" With it, the novelty is one sentence — *we replaced the LLM critic with a deterministic behavioral oracle.*
- **Contributions:** (1) the factorization argument + its formal recall/precision decomposition, and the specific claim that **a non-generative disposer** (not the agent split per se) breaks the coupling; (2) the **gate-neutrality corollary** — gap-dictation is not eliminated but *relocated* to proposer recall, escaping the FP arm and exposing the FN arm — measured via per-pair **FP-arm/FN-arm decomposition**; (3) **B-V2P**, a behavioral analogue of static V2P, with a gap-stratified paired-McNemar evaluation; (4) empirical evidence that decoupling escapes the single-stage trade; (5) an honest accounting of the compute price of evidence-gating.
- **Why it lands:** it reuses the field's own evaluation discipline (paired eval, perturbation, ablation, McNemar — cf. VulTriage Appendix C) but moves the unit of analysis from *source code* to *running behavior* — the rung the cited work gestures toward as future work.

---

## Quality Gate 1 (design-principle alignment)

| Question | Answer |
|---|---|
| Enhances human capability? | Yes — it measures and raises the engine's reach (proposal recall) while keeping confirmation evidence-gated; it amplifies a bounty hunter rather than replacing judgment. |
| Supports focus / avoids distraction? | Yes — impact-gating + funnel efficiency keep operator attention on confirmed findings; over-proposal cost is measured, never shipped as noise. |
| Transparent (glass-box)? | Yes — every claim traces to a funnel artifact; the disposer is deterministic and inspectable; the agent proposes, the harness disposes. |

**Gate 1: PASS** (research framing; reuses the field's evaluation discipline). Research-validity gates (pre-registration of E2's metric/test/δ; recall-over-known; no imported magnitudes) are tracked in `tasks.md`.
