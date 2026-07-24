# Propose–Dispose: Decoupling Recall and Precision in Evidence-Gated Vulnerability Discovery

**Living preprint · strix program · version vP-0.3**
**Changelog (vP-0.2 → vP-0.3):** added the dynamic-confirmation / autonomous-exploitation lineage to §2 and reframed novelty as *modality applied to the trap papers' own stated objective* (not invention of confirm-by-execution); made the independent-derivation claim *auditable* against the dated strix provenance trail; bounded `Prec_gate ≈ 1` to paired B-V2P targets (the oracle-soundness limit); added synthesized-patch independence/blinding; pre-registered a McNemar discordant-pair power target. *(Prior: vP-0.1 → vP-0.2 corrected the recall decomposition to `R_e2e = R_prop · S_gate`, added `S_gate` as a second false-negative locus, and reframed the convergent derivation as independent-not-prior.)*
**STATUS: PRE-EMPIRICAL.** This version consolidates the architecture, hypotheses, and *pre-registered* evaluation design into a single source of truth. **No empirical results are reported yet** — §6 (Results) is a set of pre-registered stubs to be populated by experiments E1–E4. Every claim is tagged in the Claims Ledger (Appendix A); nothing is asserted as validated until its evidence lands. This is deliberate: the project's own doctrine — *the agent proposes, the harness disposes; no claim without evidence* — applies to this paper.

> **Sources of truth.** This document is the **scientific/narrative** source of truth (thesis, hypotheses, method, results, framing). The **execution** source of truth is the strix `.agents/specs/` program (the phase triplets + the `propose-dispose-instrumentation` and `propose-dispose-validation` specs); this paper *references* those, it does not fork them. The earlier `conceptual/` working drafts (proposal v0.1→v0.4, PM review notes) are **superseded** by this consolidation and preserved as Design Provenance (Appendix B).

---

## Abstract

Large-language-model (LLM) vulnerability detectors are caught in a single-axis precision/recall trap: tuned for recall they hallucinate vulnerabilities on patched code (catastrophic false-positive rates); tuned with explicit reasoning they suppress false alarms only by missing real bugs. We observe that this trap is a property of making **one binary decision in one component**, and that even multi-agent systems which *split* proposing from judging remain trapped — because their judge is still a language model re-reading the same artifact. We present **propose–dispose**, an architecture that factorizes vulnerability discovery into a high-recall **proposal** stage (an LLM agent) and a high-precision **confirmation** stage owned by a **non-generative, evidence-producing disposer** — a deterministic harness that *observes runtime behavior* (an out-of-band callback correlated to a minted token, a differential across authenticated identities, a race interleaving) rather than re-judging code. Because precision is owned by the harness and not a model, proposal recall can be pushed aggressively without leaking into confirmation precision; the only cost of over-proposing is compute, not credibility. We formalize end-to-end recall as `R_e2e = R_prop · S_gate`, the product of proposal recall (owned by the proposer) and gate sensitivity (owned by the harness), and we show the decoupling claim separately: confirmation precision `Prec_gate` stays ≈ 1 *independent of* `R_prop`, because a different, non-generative component owns it. A definitional containment — the gate can only remove proposals, never add findings (`C ⊆ P`) — has the consequence that gap-dictation is not eliminated but **relocated**: the architecture escapes the false-positive arm of the trap while the false-negative arm is inherited by the proposer as a recall problem. We instantiate propose–dispose in **strix**, an evidence-gated bounty engine, and define **Behavioral-V2P (B-V2P)**, a behavioral analogue of static vulnerable-vs-patch evaluation in which the same application is deployed at a vulnerable commit and its minimal-diff security fix and the *harness* — not the model — is asked to flip its verdict. We pre-register four hypotheses and a gap-stratified paired-McNemar evaluation. **Empirical results are forthcoming; this version reports design and pre-registration only.**

---

## 1. Introduction

Automated vulnerability detection with LLMs has advanced rapidly, but a line of recent work shows the advances may be illusory. Fine-tuned detectors achieve high scores when a vulnerable function is contrasted with unrelated benign code, yet collapse when the negative is the *patched version of the same function* — they pattern-match surface features rather than reasoning about the security-critical delta [SemanticTrap]. The failure has a characteristic shape: **without explicit reasoning, models reach high recall with a catastrophic false-positive rate** (they flag patched code as vulnerable because it still "looks" vulnerable); **with explicit reasoning, false alarms drop but recall collapses** (they miss real bugs). This is a single-axis trade, and it is the central obstacle to reliable automated security analysis.

The trap is a property of the *decision structure*, not merely of model quality. A detector that makes one binary judgment over one artifact must trade its two error types against each other. Context augmentation (structural, retrieval, and self-explanation streams) improves the judgment but does not break the trade: even state-of-the-art augmentation tops out near a coin-flip-plus on hard pairs [VulTriage]. Multi-agent systems that *separate* a proposing agent from a judging agent [GPTLens, VulTrial, ConColl] do not break it either, and the reason is structural: **their disposer is itself a language model judging the same artifact the proposer judged.** Precision is still owned by a model reading code, so pushing the proposer harder still leaks into the verdict.

**Our move.** We factorize the decision and replace the LLM critic with a **non-generative disposer**. The proposer (an LLM agent) is optimized for recall and is permitted — encouraged — to over-propose. The disposer is a deterministic harness that *executes the target and observes behavior*: it confirms a candidate only when it produces an artifact a model cannot fabricate by reasoning harder — an out-of-band callback correlated to a minted token, a response differential across authenticated identities, a concurrent-redemption state delta. Confirmation requires `evidence_class ≠ none`. Because the harness, not a model, owns precision, raising proposal recall cannot lower confirmation precision.

**Contributions.**
1. **The factorization argument** and its formal recall decomposition (`R_e2e = R_prop · S_gate`, with `Prec_gate` ≈ 1 held *independently* of `R_prop` — the precision-decoupling claim, not a factor of the identity), with the specific claim that the **non-generative disposer** — not the agent split per se, and not confirm-by-execution per se (established in dynamic analysis, §2) — is what breaks the coupling *for the Semantic-Trap regime* (§3). *(architectural)*
2. **The gate-neutrality corollary** (`C ⊆ P`): gap-dictation is not eliminated but relocated to the proposer's recall, so the architecture escapes the false-positive arm of the trap and exposes the false-negative arm as the true ceiling (§3.3). *(architectural; consequence under test)*
3. **Behavioral-V2P (B-V2P)**, a behavioral analogue of static V2P evaluation, and a gap-stratified paired-McNemar protocol that moves the unit of analysis from source code to running behavior (§5). *(method)*
4. **A pre-registered evaluation** (H1–H4, §4) instantiated in strix, with an honest accounting of the compute price of evidence-gating. *(design; results pending — §6)*

This version of the paper presents 1–4 as **design and pre-registration**. The empirical confirmation or refutation is the subject of §6 and is **not yet reported**.

---

## 2. Background & Related Work

**The Semantic Trap [SemanticTrap].** A study of fine-tuned decoder-only LLMs under vanilla and chain-of-thought (CoT) supervised fine-tuning identifies three measurable symptoms of surface-pattern reliance: (i) *pairing-sensitive performance* — strong on vuln-vs-unrelated (V2N), collapsing on vuln-vs-patch (V2P); (ii) *gap-dictated decisions* — accuracy correlates with the textual/CodeBLEU distance between vuln and patch (weak but systematic, |ρ|<0.1, p<0.05), not with security logic; (iii) *fragility to semantic-preserving perturbation*. Its reasoning-failure taxonomy (C1–C8) splits by direction: **C1 (control-flow misinterpretation) and C2 (API/behavior hallucination) drive false positives; C5 (CWE/category misapplication) and C6 (concurrency blind spots) drive false negatives**, with C5 most frequent overall. We treat the taxonomy as an LLM-as-judge artifact — "targets C5" means "targets the C5-*described* failure mode." The paper's own CoT arm caveat — that its apparent escape from gap-dependency is "partly compatible with a floor effect arising from lower recall and should not be read as direct evidence of escaping the trap" — is consistent with our reading of CoT as mitigation, not escape.

**Context augmentation [VulTriage].** Triple-path augmentation (Control: AST/CFG/DFG verbalized; Knowledge: CWE retrieval; Semantic: LLM self-summary) raises pair discrimination and lowers FPR, but the best configuration reaches only ≈0.64 accuracy / 0.69 F1 on the PrimeVul hard-pair set, with the LLM cast explicitly as a "static code auditor." Augmentation helps the judgment; it does not make a single-stage classifier reliable. (Its Appendix C uses paired **McNemar** tests — the protocol we adopt as our primary test, §5.)

**Multi-agent LLM critics.** GPTLens (auditor proposes, critic scores), VulTrial (four-role courtroom debate), and ConColl (confidence-gated single → RAG → multi-agent cascade) all decouple proposal from disposition, and all remain trapped — on PrimeVul hard pairs they sit at ≈0.51–0.54 accuracy, barely above the 0.50 floor. **In every one the disposer is a language model re-judging the same artifact**, so the precision/recall coupling survives the agent split.

**Dynamic confirmation and autonomous exploitation.** Confirming a candidate by *executing the target and observing behavior* is established security practice, not a contribution of this paper: dynamic application security testing (DAST), out-of-band application-security testing via interaction oracles (e.g., OAST listeners such as Burp Collaborator / interactsh), and differential authorization testing (e.g., Autorize-style cross-identity replay) all gate on produced artifacts rather than code inspection. A recent line of LLM-driven autonomous-exploitation agents likewise *executes* candidate exploits to confirm them [AutoExploit]. We **import** this modality; we do not claim to originate it. Our contribution relative to this lineage is twofold: (i) the formal recall/precision **factorization** (`R_e2e = R_prop · S_gate`; `Prec_gate` decoupled from `R_prop`), which names *why* an evidence-owning disposer breaks the single-stage trade; and (ii) bringing confirm-by-execution to bear on the **specific failure** the static-detection literature diagnoses — the Semantic Trap — rather than to bug-finding in general.

**Positioning.** [SemanticTrap] states the objective directly — detection must move "from how the code *looks* to how the code *behaves* from a security perspective" and "should not rely on code alone" — yet pursues "behaves" through *statically*-derived control/data-flow and execution *paths*; it does not propose runtime grounding (that gap is implied, not stated as future work). [VulTriage] reaches the ceiling of *static* augmentation (≈0.64 accuracy) with the LLM cast explicitly as a "static code auditor." We take their stated objective literally and change the **modality**: we ground "behaves" in *executed* runtime behavior, observed by a deterministic harness rather than inferred by a model. The novelty is therefore not confirm-by-execution itself (established; see above) but **its use as the disposer that resolves the precise trap these papers diagnose** — and the factorization that explains why it works.

| Rung | Representative | Unit of analysis | Disposer | Trap broken? |
|---|---|---|---|---|
| Raw tokens | PrimeVul prompting | static source | model | No |
| + static structure | VulTriage | static AST/CFG/DFG | model | No (≈0.64 acc ceiling) |
| + distilled reasoning / CoT | Semantic Trap (CoT arm) | static source + CoT | model (self) | No (floor-effect "escape") |
| + multi-agent factorization | GPTLens / VulTrial / ConColl | static source | **another LLM** | No (≈0.51–0.54 acc) |
| **+ observed runtime behavior w/ evidence** | **strix (propose–dispose)** | **running deployment** | **deterministic harness** | **claim under test (H1)** |

The fourth rung is load-bearing: without it the contribution reads as "GPTLens with extra steps." With it, the novelty is one sentence — **we replace the LLM critic with a deterministic behavioral oracle of the kind dynamic analysis already uses, and apply it to the Semantic Trap the static-detection literature could not escape.**

---

## 3. The Propose–Dispose Architecture

### 3.1 Factorization and the formal decomposition

For a target with ground-truth-labeled vulnerability set `V`:

- Proposals `P` — candidates the agent emits for investigation.
- Confirmations `C ⊆ P` — proposals the harness backs with `evidence_class ≠ none`.
- **Proposal recall**: `R_prop = |P ∩ V| / |V|`
- **Confirmation precision (gate leakage)**: `Prec_gate = |C ∩ V| / |C|` (≈ 1 by design; *measured*, not assumed)
- **Gate sensitivity (confirmation recall)**: `S_gate = |C ∩ V| / |P ∩ V|` — of the true vulns the proposer *proposed*, the fraction the harness *confirmed*. (Distinct from `Prec_gate`: same numerator, denominator `|P∩V|` vs `|C|`.)
- **End-to-end recall**: `R_e2e = |C ∩ V| / |V| = R_prop · S_gate` — proposal recall times gate sensitivity.

Two distinct claims follow, and the paper keeps them separate. **(i) Precision decoupling (the trap-break, H1):** in a single-stage detector raising recall lowers precision; in propose–dispose `Prec_gate` is owned by the **harness**, not the proposer, so raising `R_prop` cannot lower `Prec_gate` — a *different* component owns it. **(ii) The recall identity:** `R_e2e = R_prop · S_gate` shows end-to-end recall is the product of two recall terms — what the proposer surfaces (`R_prop`) and what the harness can actually fire on (`S_gate`) — neither of which is `Prec_gate`. Conflating `S_gate` with `Prec_gate` would overstate `R_e2e`; we report both `S_gate` and `Prec_gate` off the funnel. **The only cost of over-proposing is compute** (more harness runs, tracked as `funnel_efficiency = harness_runs / |C|`), **not credibility** (false reports).

### 3.2 The non-generative disposer (the novelty)

The disposer does not re-read the code. It is a deterministic, evidence-producing harness that observes runtime behavior and emits a typed `evidence_class ∈ {diff, callback, reachability, race_result, none}`. Confirmation requires a non-`none` artifact a model cannot fabricate by reasoning. This is the single axis on which propose–dispose differs from the multi-agent LLM-critic systems of §2.

A typed artifact establishes that a behavior *occurred*, not that it is *security-relevant* in isolation: legitimate functionality (an intended URL fetch, intended per-identity data) can also fire an evidence class. The B-V2P design (§5) controls this by construction — the same application at vuln and patch commits cancels intended behavior, so a *flip* across the pair isolates the security delta. Accordingly, the `Prec_gate ≈ 1` claim is demonstrated **on paired B-V2P targets**, where intended behavior is differenced out; it is **not** asserted for arbitrary unpaired deployment, where distinguishing vulnerable from intended behavior may require additional impact criteria. This boundary is itself the most informative thing E1 measures.

### 3.3 The gate-neutrality corollary (load-bearing)

`C ⊆ P`: the gate can only *remove* proposals, never *add* findings. Therefore the gate **cannot rescue a vulnerability the proposer never proposed.** Any gap-dictation that lives in the proposer — failing to propose a subtle vuln because it *looks* benign (small surface gap) — is inherited end-to-end as a false negative.

Consequently, gap-dictation is **not eliminated but relocated**:
- **False-positive arm — escaped.** The gate refuses to confirm patched code (no behavioral artifact fires), so the catastrophic-FPR symptom of the trap does not occur.
- **False-negative arm — inherited.** The proposer's gap-dictation surfaces as missed proposals on small-gap targets, coinciding with the C5/C6 false-negative regime and with the recall interventions of §5.

Note this places the false-negative arm in **two** loci, not one. `R_e2e = R_prop · S_gate` has two recall terms below 1: a **proposer miss** (`R_prop < 1` — the subtle vuln was never proposed, the gap-dictation case above) and a **gate miss** (`S_gate < 1` — the vuln *was* proposed but the harness could not produce its artifact, e.g. a genuinely vulnerable blind SSRF whose callback is egress-filtered, so the OOB oracle returns *unconfirmed*). The first is the proposer's recall ceiling; the second is the harness's sensitivity ceiling. Both are measured directly off the funnel; the headline below concerns the proposer locus, but `S_gate` is reported alongside it so the ceiling claim is exact.

The honest headline is therefore *not* "strix escapes gap-dictation," but: **strix escapes the false-positive arm of gap-dictation; the false-negative arm is the proposer's recall problem.**

### 3.4 strix instantiation: the disposer arsenal

strix is an evidence-gated bounty engine built on four primitives and an impact gate; the propose–dispose disposers are deterministic harnesses each neutralizing a specific LLM failure mode:

| Failure mode (from [SemanticTrap]) | Arm | Disposer (strix phase) | Evidence |
|---|---|---|---|
| C2 API/behavior hallucination ("the SSRF fired") | FP | **P3 OOB oracle** (Phase 2): mint token → correlated callback | `callback` |
| C1 control-flow misread / C3 scope isolation | FP / FN | **P4 reachability** (Phase 3) route→handler→auth-mw→sink | `reachability` |
| broken authorization (IDOR/BFLA) | FP | **P2 differential** (Phase 1): cross-identity response diff | `diff` |
| C6 concurrency / TOCTOU | FN | **Phase-4 race harness**: N-copy state-delta + commit-count | `race_result` |
| C5 business-logic / category | FN | **Phase-5 orchestrator**: executed sequence reaching a model-impossible state | diff ∨ callback ∨ race_result |

**The architecture is the thesis embodied.** Phase 5 is propose–dispose stated in code: the agent *proposes* a journey/state model (every field tagged `agent-proposed`); deterministic harnesses *dispose* by executing violation tests; an evidence gate promotes a violation only with a typed artifact *and* a reached model-impossible state; and "no self-confirmation" — `∀ proposed invariant: confirmation originates from a harness, never from the proposing model` — is a property-based-tested invariant. The whole program (P0 hardening + impact gate → P1 identity/differential → P2 OOB → P3 inventory/reachability → P4 race → P5 business-logic) is the disposer substrate this paper measures.

---

## 4. Hypotheses (pre-registered)

| # | Hypothesis | Falsifier |
|---|---|---|
| **H1 — tradeoff break** | As proposal aggressiveness rises, single-stage mode shows recall↑/precision↓ (the trap); propose–dispose shows `R_e2e`↑ while `Prec_gate` stays ≈ constant. | `Prec_gate` falls materially as `R_prop` rises (gate leaks under over-proposal). |
| **H2a — FP-arm win** | *Main effect (primary):* on B-V2P pairs the strix pipeline is more pairwise-correct than a single-stage proxy (gap-stratified paired McNemar, one-sided). *Mechanism fingerprint (secondary, power permitting):* the margin widens as surface gap shrinks. | strix not significantly more pairwise-correct on the main effect. (Underpowered interaction is reported as such, not as falsification.) |
| **H2b — FN-arm limit** | Proposer recall is gap-dependent (drops on small-gap pairs) and, because the gate is neutral, is inherited end-to-end as false negatives. | Proposal recall flat across the gap — a stronger, more publishable result. |
| **H3 — interventions lift recall** | Knowledge-Path raises `R_prop` on C5-attributed misses; the C-checklist on C6/C7; Control-Path on C3 (reachability/context). Single-intervention ablation, per FN-category. | An intervention shows no significant `R_prop` gain on its FN-targeted category. |
| **H3b — Control-Path precision effect is efficiency** | Control-Path lowers C1-attributed false-positive *proposals*, improving `funnel_efficiency` without materially changing `R_prop`. | Control-Path's only measurable effect is on `R_prop`. |
| **H4 — perturbation invariance** | Cosmetic perturbation of the live target's responses leaves strix verdicts invariant; a static-proxy classifier degrades. | strix verdict variance ≈ static proxy's. |

---

## 5. Methodology / Experimental Design

**Behavioral-V2P (B-V2P).** Static V2P pairs a vulnerable function with its patch. B-V2P pairs a *deployed* application at its vulnerable commit and its security-fix commit, each containerized and run live; the experiment asks whether the *harness* flips its verdict across the pair. The corpus is **small-gap-biased** (the primary test needs discordant small-gap pairs, not breadth), labeled with ground-truth `V` (recall reported as *recall-over-known*), and minimal-diff — where no clean public single-commit fix exists, a **minimal patch is synthesized** (a single security-logic change), which is preferable for the discriminating pairs because it controls the surface gap to a minimum. To prevent the synthesized patch from trivially guaranteeing the flip, minimal patches are authored **independently of the harness's probe design** (the patch encodes the security-logic fix a maintainer would write, decided without reference to which artifact the disposer fires on); pairs whose patch was co-designed with the harness are labeled and used only as walking-skeleton (M0) checks, not as evidential pairs in E2. Coverage: ≥1 pair per primitive — IDOR/BFLA (P1/P2), SSRF/XXE (P3) now; race (P4) and business-logic (P5) as soft-edged additions.

*Seeds (verified).* Discriminator: **open-webui IDOR (CVE-2024-7041)** via a synthesized one-line ownership-check patch (no clean public single-commit fix exists). H1/OOB-callback showcase: **Flowise SSRF (CVE-2026-31829, ≤3.0.12 → 3.0.13)**. Both CVE IDs were verified against NVD (CVE-2024-7041 = open-webui v0.3.8, IDOR/CWE-639; CVE-2026-31829 = Flowise <3.0.13, SSRF/CWE-918).

**Instrumentation.** A glass-box funnel records every `proposal → harness run → confirmation → report` transition as a `ProposalRecord` (endpoint/param, declared CWE, C1–C8 self-check answers, harness verdicts + `evidence_class`, cost), from which `R_prop`, `Prec_gate`, `R_e2e`, `funnel_efficiency` are pure functions. *(Built in the `propose-dispose-instrumentation` unit; consumed here.)*

**Proposal-context interventions (recall layer).** Three flag-gated, independently-ablatable streams targeting the false-negative drivers: Knowledge-Path (per-class CWE priors → C5), C1–C8 self-interrogation checklist (→ C6/C7), Control-Path (verbalized reachability graph → C3). Control-Path's effect on C1 (an FP-driver) is billed as `funnel_efficiency`, not recall (H3b).

**Baselines.** (a) A **single-stage agent-as-judge** mode (harness disabled, agent self-confirms) — *research-only*, build-time/entrypoint gated, with a regression test asserting it is OFF in production (it is the one component touching the forbidden self-confirm path and is quarantined out of the product); (b) a static/CoT proxy classifier; (c) optionally an LLM-critic baseline (GPTLens-style) under the same gate, so we measure against the multi-agent rung, not only single-stage. The within-system ablation (strix with harness vs. the quarantined self-confirm mode, all else fixed) is the cleanest causal test of the harness's contribution and is treated as primary; the external proxies are secondary.

**Primary test.** Gap-stratified **paired McNemar** (strix pipeline vs single-stage proxy on the same pairs), main effect primary, small-gap-widening as the mechanism fingerprint. Difference-of-correlations with bootstrap CIs is secondary/illustrative. The gap metric, the test, and any equivalence margin δ are **pre-registered before outcomes are observed**. The minimum discordant-pair count is **pre-registered**: a power analysis for the one-sided paired McNemar at the registered effect size and α is recorded before any E2 outcome is observed, and E2 is not read until the corpus reaches that discordant-pair target (under-powered, the main effect is reported as inconclusive, never as falsification). Recall is recall-over-known; no claim imports the cited papers' magnitudes (they fix the trap's *shape*, not its coordinates in this regime).

---

## 6. Results — PRE-REGISTERED · PENDING EMPIRICAL EVIDENCE

> **This section is intentionally empty of findings.** Each experiment below states its pre-registered test and decision criterion; the result tables are placeholders to be populated only after the experiments run. Per the project doctrine, no result is asserted here in advance of its evidence. Status of each: **`pending-evidence`** (see Claims Ledger, Appendix A).

**M0 — walking skeleton (first datapoint).** On the open-webui IDOR synthesized-minimal-patch pair: did the P2 differential harness flip vuln→fixed *while the agent's raw proposal did not*? `[PENDING]` — if the raw proposal already flips cleanly and reliably, the gate is doing less than assumed; that outcome is recorded, not hidden. (Note: this seed's patch is co-designed with the IDOR probe, so M0 is a smoke test, not an E2 evidential pair — see §5.)

**E1 — tradeoff curve (H1).** Sweep proposal aggressiveness; plot recall vs. precision for single-stage vs. propose–dispose. Decision: H1 supported iff `Prec_gate` stays ≈ constant as `R_e2e` rises in propose–dispose while single-stage shows the recall↑/precision↓ trade. **Primary watch: `Prec_gate` leakage, including intended-behavior false confirmations (§3.2).** Result: `[PENDING]`.

**E2 — gap-dictation (H2a/H2b).** Gap-stratified paired McNemar (primary, over the pre-registered discordant-pair target); per-pair FP-arm/FN-arm decomposition; correlations illustrative with bootstrap CIs. Decision: H2a supported iff strix is significantly more pairwise-correct than the proxy on the main effect; H2b characterized by proposer-recall vs. gap. Result: `[PENDING]`.

**E3 — intervention ablation (H3/H3b).** Full vs −Control vs −Knowledge vs −Checklist; two readouts (per-FN-category `R_prop`; `funnel_efficiency` with C1-FP-proposal rate). Result: `[PENDING]`.

**E4 — perturbation invariance (H4).** Semantic-preserving perturbation of live responses; strix vs static-proxy verdict variance. Result: `[PENDING]`.

*(Race (C6) and business-logic (C5) experiments are soft-edged behind Phases 4/5 and will extend E1–E4 once those disposers land.)*

---

## 7. Threats to Validity

- **Recall denominator.** `V` is labeled-known-only; absolute recall is unknowable. Reported as recall-over-known with the unknown-unknown caveat.
- **Behavior ≠ vulnerability (oracle soundness).** A fired evidence class proves observed behavior, not security-relevance per se; B-V2P pairing differences out intended behavior so a verdict *flip* isolates the security delta. The `Prec_gate ≈ 1` claim is therefore scoped to paired targets; unpaired production confirmation is out of scope for this study's precision claim.
- **B-V2P minimal-diff fidelity.** Real fix commits bundle unrelated changes; synthesized minimal patches isolate the security delta so verdict flips are attributable to it.
- **Synthesized-patch circularity.** Team-authored minimal patches risk encoding exactly what the harness probes. Mitigation: patch authored independently of harness probe design; co-designed pairs are quarantined to M0 (smoke test), excluded from the E2 evidential set.
- **Over-proposal compute cost.** The doctrine's price is harness runs; `funnel_efficiency` is reported as a first-class result, not a footnote.
- **Gate leakage is the real risk.** If aggressive proposals get spuriously confirmed, `Prec_gate < 1` and the thesis weakens; E1 watches this directly — it is the most important number in the study.
- **Single-stage fairness / floor effects.** The baseline is constructed to avoid the floor-effect confound the Semantic Trap authors flag (dynamic range matched).
- **Shape not coordinates.** The cited papers measure fine-tuned 7–8B classifiers over static C/C++ pairs; their magnitudes are not transferred — the single-stage baseline is self-measured.
- **LLM-as-judge taxonomy.** C1–C8 are evaluator-produced descriptions; "targets C5" = "the C5-described failure mode."
- **Correlation power / corpus size.** A per-pair gap-correlation needs many pairs; the primary test is the paired McNemar (needs discordant small-gap pairs, not breadth). The minimum discordant-pair count is pre-registered from a power analysis before outcomes are read; no tight ρ from tiny n; an under-powered main effect is reported as inconclusive, not as a refutation.

---

## 8. Discussion

If H1 holds, the contribution is a structural escape from a trade the literature treats as fundamental: not a better single-stage classifier and not another multi-agent judge, but the replacement of the LLM critic with a deterministic behavioral oracle — a modality dynamic analysis already uses, here applied to the precise trap the static-detection literature could not escape. If H1 is refuted — if `Prec_gate` leaks under over-proposal — the most likely cause is a disposer that is not as non-generative as claimed (e.g., intended-behavior confirmations the impact gate fails to exclude), and that is itself a precise, publishable finding about where evidence-gating actually binds.

The deeper result is the **relocation, not elimination, of gap-dictation** (§3.3). Evidence-gating buys precision unconditionally but buys recall *nothing*: a subtle vulnerability the proposer never proposes is never confirmed. This reframes the engineering frontier — the recall ceiling of an evidence-gated agent is the product `R_prop · S_gate`: what the proposer surfaces *and* what the harness can fire on. Proposal recall (`R_prop`) is the dominant, model-driven term and the open problem the recall interventions (§5, H3) target the false-negative drivers of; gate sensitivity (`S_gate`) is the harness-side term, reported off the funnel so a recall loss is correctly attributed to proposer vs. gate rather than blamed wholesale on the proposer. The funnel likewise measures the compute cost of over-proposing honestly. It also explains why the program front-loads the precision-owning harnesses (P2/P3/P4) and treats the proposal layer as the open problem.

Finally, the architecture is not merely a testbed for the thesis; Phase 5 *is* the thesis in code (agent proposes the model, harnesses dispose, evidence gate, no-self-confirmation invariant). That coincidence is evidence the doctrine is implementable end-to-end, independent of whether the headline empirical claim ultimately holds.

---

## 9. Conclusion

We have presented propose–dispose — a factorization of LLM vulnerability discovery into a high-recall proposer and a high-precision, non-generative behavioral disposer — argued that it breaks the single-stage precision/recall trade by relocating precision to a deterministic harness, and shown the honest consequence: the false-positive arm of gap-dictation is escaped while the false-negative arm becomes the proposer's recall problem. We defined Behavioral-V2P and pre-registered a gap-stratified paired-McNemar evaluation in the strix engine. **The empirical validation is forthcoming**; this version reports the architecture and the pre-registered design. When the evidence lands (§6), it will be added under the Claims Ledger discipline that governs this document.

---

## Appendix A — Claims Ledger

> Every load-bearing claim, tagged. `architectural` = true by construction of the system; `prior-work` = established in cited literature; `under-test` = a hypothesis this work will decide; `pending-evidence` = asserted only once its experiment runs. **No `pending-evidence` row may be written as a result until its experiment completes.**

| Claim | Tag |
|---|---|
| Single-stage LLM detection exhibits a precision/recall trap with the three symptoms | `prior-work` [SemanticTrap] |
| Context augmentation improves but does not make single-stage reliable (≈0.64 acc ceiling) | `prior-work` [VulTriage] |
| Multi-agent LLM-critic systems remain trapped (≈0.51–0.54 acc) | `prior-work` |
| Confirm-by-execution is established dynamic-analysis practice; the contribution is the factorization + its application to the Semantic Trap | `prior-work` (modality) + `architectural` (factorization) |
| `R_e2e = R_prop · S_gate` (recall identity); `Prec_gate ≈ 1` held independently of `R_prop` (precision decoupling) | `architectural` |
| The disposer is non-generative; precision is owned by the harness, not a model | `architectural` (strix design) |
| `C ⊆ P` (gate neutrality): the gate removes, never adds | `architectural` |
| Independent derivation of the disposer thesis (strix specs 2026-06-14 predate paper discovery) | `architectural` provenance; **auditable** via dated program records (Appendix B.1) |
| Gap-dictation is relocated to recall (FP-arm escaped, FN-arm inherited) | `architectural` premise; **end-to-end consequence** `under-test` (H2a/H2b) |
| `Prec_gate ≈ 1` holds on paired B-V2P targets; unpaired production precision is out of scope | `architectural` (paired); **unpaired** out of scope |
| Propose–dispose breaks the precision/recall trade | `under-test` (H1) |
| Behavioral grounding beats surface gap on small-gap pairs | `under-test` (H2a) |
| Proposer recall is the true ceiling (gap-dependent) | `under-test` (H2b) |
| Gate sensitivity `S_gate < 1` is a second FN locus distinct from proposal recall | `architectural` premise; **magnitude** `under-test` (measured off funnel) |
| Each proposal intervention lifts recall on its FN-category | `under-test` (H3/H3b) |
| strix verdicts are perturbation-invariant vs a static proxy | `under-test` (H4) |
| Any quantitative result for E1–E4 / M0 | `pending-evidence` |

---

## Appendix B — Design Provenance

This thesis was not adopted from the literature; it was reasoned to independently and *then* found to converge with it — and it was sharpened by adversarial review across roles (visionary, PM/architect, implementer, research synthesis). The record matters because each sharpening corrected an over-claim:

1. **Convergent (independent) derivation — auditable.** The strix propose–dispose doctrine and impact-gating were reasoned out **without reference to** the Semantic Trap and VulTriage papers, which the author encountered only afterward. The independence is checkable against the program's dated provenance trail, not asserted: the strix program initialized on **2026-06-14** with *"agent-proposes / harness-disposes — the LLM never self-confirms a finding"* and *impact-gating with a typed `evidence_class`* recorded as **founding** architecture patterns (`memory_bank/MASTER_CONTEXT.md`, Phase 0), and the propose–dispose proposal emerged later, mid-Phase-3 (the engine's Phase-0→3 build predates the literature review; the proposal first appears as a separate addendum during Phase-3 close-out). We make **no** claim of temporal priority over the papers — SemanticTrap (arXiv 2601.22655, v1 Jan 30 2026) and VulTriage (arXiv 2605.09461, May 10 2026) both predate the 2026-06-14 specs — only of **independent derivation**: the disposer thesis was an engineering decision for a bounty engine, and the static-detection literature was encountered afterward as an external convergence check. Two independent routes — one engineering, one academic — landing on "the model cannot self-confirm; gate on observed evidence" de-risks the *premise* (not the empirical magnitudes, which remain `under-test`).
2. **Stats escalation (v0.3→v0.4).** The original H2 tried to *prove a null* (`ρ≈0`) — corrected to a difference-of-correlations / paired-McNemar framing with pre-registration and power-checking.
3. **Aim correction.** A deterministic harness cannot exhibit gap-dictation *by construction* (it reads behavior, not tokens); testing it is near-vacuous. The contestable locus is the proposer — which led to the **H2a/H2b split** and the gate-neutrality corollary (§3.3): the honest claim is the FP-arm escape, not a flat "escapes the trap."
4. **Non-generative-disposer positioning.** The factorization is not the novelty (multi-agent critics already factorize); the **non-generative disposer** is. Naming the multi-agent rung explicitly (§2) preempts "isn't this GPTLens with extra steps?" — and naming the dynamic-analysis lineage (§2) preempts "isn't the disposer just DAST?": the contribution is the factorization plus the trap-specific application, not the modality.
5. **C-category targeting.** Proposal interventions raise recall, so they target the *false-negative* drivers (C5/C6/C7); C1's effect is a funnel-efficiency gain, not recall (H3/H3b). C2's other FP role is disposed at the gate (the OOB oracle), completing the taxonomy.

The superseded `conceptual/` drafts (proposal v0.1, v0.2, v0.3, v0.4; the stats patch; the PM response and escalation notes; the manifest-integration note) are retained in the program archive as the full provenance trail.

---

## Appendix C — Implementation & Reproducibility (pointer, not a fork)

The execution source of truth is the strix `.agents/specs/` program. This paper consumes, and does not duplicate, the following:

- **Disposer substrate (complete):** Phase 0 (foundation hardening + impact gate / `evidence_class`), Phase 1 (P1 identity store + P2 differential engine), Phase 2 (P3 self-hosted OOB oracle), Phase 3 (attack-surface inventory + P4 reachability seam + parameter classifier).
- **Disposer substrate (planned):** Phase 4 (race harness; C6 disposer), Phase 5 (business-logic orchestrator; C5 disposer, and the doctrine embodied).
- **`propose-dispose-instrumentation`** (`type: unit`, product DAG) — the funnel/`ProposalRecord` (M1) and the proposal-context assembler (M3). Built once, reused by the engine and by this evaluation.
- **`propose-dispose-validation`** (`type: research`, non-gating) — the B-V2P corpus (M2), the quarantined single-stage ablation mode (M4), and experiments E1–E4 + this paper (M5). Its `spec.md` (canonical Spec-Architect format) and `tasks.md` carry the buildable detail; this paper carries the science.
- **Reproducibility primitives:** dockerized B-V2P seeds at named commits (CVE-2024-7041; CVE-2026-31829); the funnel log as the per-claim artifact trail (Appendix A discipline: every reported number resolves to a `ProposalRecord`).

---

## References

- **[SemanticTrap]** Huang, Sun, Zhang, Yang, Liu, Liu. *Do Fine-Tuned LLMs Understand Vulnerabilities? An Investigation into the Semantic Trap.* arXiv:2601.22655 (v1 Jan 30 2026).
- **[VulTriage]** Tang et al. *VulTriage: Triple-Path Context Augmentation for LLM-Based Vulnerability Detection.* arXiv:2605.09461 (May 10 2026). (github.com/vinsontang1/VulTriage)
- **[GPTLens]** Hu et al. *Large Language Model-powered smart contract vulnerability detection: New perspectives.* TPS-ISA 2023.
- **[VulTrial]** Widyasari et al. *Let the Trial Begin: A Mock-Court Approach to Vulnerability Detection using LLM-based Agents.* ICSE 2026.
- **[ConColl]** Tsai et al. *A sequential multi-stage approach for code vulnerability detection via confidence- and collaboration-based decision making.* EMNLP 2025.
- **[PrimeVul]** Ding et al. *Vulnerability Detection with Code Language Models: How Far Are We?* arXiv:2403.18624.
- **[AutoExploit]** *PLACEHOLDER — author to insert personally verified autonomous-exploitation / agentic-pentest references (e.g., LLM-agent CVE-exploitation and autonomous-pentest literature). Not yet verified; do not autofill.*
- **strix** — evidence-gated bounty engine (GitHub: pt-act/strix). `.agents/specs/` program: phases 0–5 + `propose-dispose-instrumentation` + `propose-dispose-validation`.

---

*Living preprint vP-0.3 · pre-empirical. Results (§6) are pre-registered and pending. Maintained as the scientific source of truth for the propose–dispose program; execution truth lives in the strix specs.*
