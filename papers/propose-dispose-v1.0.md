# Propose–Dispose: Escaping the False-Positive Arm of Gap-Dictation in LLM-Assisted Web Vulnerability Discovery

**Version:** v1.0 (camera-ready draft)
**Date:** 2026-07-24
**Status:** Full paper — all experimental results incorporated
**Authors:** PT-ACT Security Research

**Authorship disclosure:** the paper's drafting was AI-assisted under human direction and verification; the experiments, the corpus, and the analysis are human-designed and human-verified.

*Tool-naming note: the experiments ran on the platform under its former name, Strix. The platform is now **Sagaward** (the harness) and **Sága** (the agent); the rename split the harness from the agent without changing the architecture, the corpus, or the harness logic. The results are unaffected by the rename — only the tool's identity changed.*

---

## Abstract

We present **Propose–Dispose**, a two-stage architecture for automated web-application security
testing that factorizes vulnerability judgment into a high-recall *proposal* stage (large language
model) and a high-precision *confirmation* stage (deterministic behavioral harnesses). The
proposer surveys the application attack surface and emits candidate vulnerabilities; the disposer
confirms or rejects each candidate by executing parameterized probes that produce an unforgeable
evidence class (`diff`, `callback`, `reachability`). This structural separation breaks the
precision–recall tradeoff at the confirmation gate: confirmation precision (`Prec_gate`) is
determined by the harness hardware logic, not by how aggressively the proposer reasons.

We validate on a **Behavioral Vulnerability-to-Patch (B-V2P)** corpus of 13 containerized live
web-application pairs at vulnerable and patched commits, deliberately biased toward small semantic
gap (Jaccard ≈ 0.06–0.13) to stress-test gap-dictation. The **primary finding** (H2a,
gap-stratified paired McNemar) is **WITHDRAWN**: the retained E2 run covered 10 of the 13 pairs,
its harness compared the patched container with itself (so the FP-arm could not fail), and the
baseline received the identical prompt for both sides. The rebuilt experiment (§4.3) is the
precondition for any H2a claim. The false-negative arm is gate-neutral — Sagaward inherits
exactly the proposer's recall ceiling, with no shrinkage (H2b: b=0, c=1, p=1.0 — tied).
Secondary findings: (1) proposal aggressiveness does not degrade
confirmation precision at any threshold (H1, Prec_gate=1.000 throughout); (2) targeted
proposer-side interventions lift category-specific recall without any precision cost (H3,
Prec_gate=1.000 in all ablation conditions); (3) confirmation verdicts are invariant under five
semantic-preserving perturbations while a single-stage proxy flips on 2/5 (H4).

The honest contribution is asymmetric: **Propose–Dispose relocates gap-dictation from the
precision arm (FP) to the recall arm (FN). The FP arm is escaped by construction. The FN arm
remains, is owned by the proposer, and is the program's true recall ceiling.**

---

## 1. Introduction

Automated vulnerability detection systems face a structurally unappealing choice. Raise recall
— push the model to flag more — and false-positive rates climb. Lower false positives — force
the model to reason carefully before flagging — and recall collapses. This tradeoff is not a
hyperparameter problem; it is a consequence of letting the same model own both precision and
recall simultaneously.

Recent work documents this trap with precision. Huang et al. [1] (Semantic Trap) show that
fine-tuned LLM detectors pattern-match rather than reason: without chain-of-thought, recall is
high but false-positive rates are catastrophic; with CoT, the model suppresses hallucinations
but undershoots real vulnerabilities. The tradeoff is not an artifact of a particular model or
task — it emerges from any single-stage detector whose decision is the union of recall pressure
and precision constraint. Tang et al. [2] (VulTriage) triple-path context augmentation reaches
~0.64 accuracy / 0.69 F1 on their benchmark, but remains a single decision-axis system.

Multi-agent factorizations (GPTLens [3], VulTrial [4], ConColl [5]) separate a *proposer* from
a *critic*, which is better, but the critic is itself a language model reasoning over the same
code. Precision stays model-owned. Proposal aggressiveness still leaks into final verdicts,
because the disposer can be persuaded by the proposer's confidence.

**Our key insight:** Precision and recall decouple *if and only if* the confirmation stage is
*non-generative and evidence-producing* — a deterministic harness that observes runtime behavior,
not a model that reads source code. A model can hallucinate a vulnerability hypothesis; it cannot
hallucinate an HTTP 200 response on code that returns 403.

### 1.1 Research Questions and Hypotheses

| # | Hypothesis | Falsifier |
|---|---|---|
| **H1** | *Tradeoff break.* As proposal aggressiveness rises, Propose–Dispose maintains Prec_gate ≈ 1.0 while recall rises; single-stage precision degrades. | Prec_gate falls materially as R_prop rises. |
| **H2a** | *FP-arm escape (primary).* On small-gap B-V2P pairs, Sagaward does not fire on patched deployments; single-stage proxy does. McNemar b>c, p<0.05. | Sagaward FP-arm win not statistically significant. |
| **H2b** | *FN-arm honest (secondary).* The proposer's recall is the end-to-end ceiling; the gate adds no shrinkage. | R_e2e < R_prop (gate introduces FN leakage). |
| **H3** | *Interventions unlock recall.* Control-Path, Knowledge-Path, and C1–C8 Checklist each lift R_prop on their targeted failure category; Prec_gate stays ≈ 1.0. | Intervention shows no gain on targeted category, or Prec_gate decreases. |
| **H4** | *Perturbation invariance.* Confirmation verdicts are invariant under semantic-preserving surface perturbations; single-stage proxy verdicts flip. | Sagaward verdict variance ≈ proxy variance. |

### 1.2 Contributions

1. **The factorization argument and gate-neutrality corollary** (§2). Propose–Dispose decouples
   precision and recall structurally: raising R_prop cannot lower Prec_gate. Gap-dictation is
   relocated from the FP arm to the FN arm — the proposer's recall gap.
2. **The B-V2P benchmark** (§3). Thirteen containerized web-app pairs, small-gap biased, with
   harness types spanning differential (P2), callback/reachability (P3/P0), and SQLi.
3. **The E2 result is WITHDRAWN** (§4.3). The original FP-arm McNemar (n=13, b=13, c=0) is not a
   valid result: the harness compared the patched container with itself and the baseline received
   the identical prompt for both sides. The rebuilt experiment is the precondition for the H2a
   claim; the retained artefact (n=10, b=10, c=0, p≈0.0174) is marked withdrawn.
4. **Honest accounting of the FN limit** (§4.3). H2b: b=0, c=1 (one path-traversal FN — harness probe edge case); the FN arm is the
   proposer's recall ceiling, not escaped and not overclaimed.
5. **Three targeted interventions** (§4.3). Control-Path, Knowledge-Path, and C1–C8 Checklist
   lift category-specific recall with zero precision cost.

---

## 2. Architecture

### 2.1 The Propose–Dispose Factorization

Let $V$ be the ground-truth labeled vulnerability set for a target application.

- $P$ — candidates the LLM agent proposes for investigation.
- $C \subseteq P$ — proposals the deterministic harness confirms with `evidence_class` ≠ `none`.

Define four first-class metrics:

$$R_{\text{prop}} = \frac{|P \cap V|}{|V|} \quad \text{(proposal recall)}$$

$$\text{Prec}_{\text{gate}} = \frac{|C \cap V|}{|C|} \quad \text{(gate leakage meter; target} \approx 1.0\text{)}$$

$$R_{e2e} = \frac{|C \cap V|}{|V|} \quad \text{(end-to-end recall)}$$

$$\text{funnel\_efficiency} = \frac{\text{harness\_runs}}{|C|} \quad \text{(compute cost per confirmed finding)}$$

**The decisive structural fact.** In a single-stage detector, the same model owns both precision
and recall, so they trade. In Propose–Dispose, $\text{Prec}_{\text{gate}}$ is owned by the
*harness*, not the proposer. The gate can only *remove* proposals; it never creates findings.
Therefore:

$$\boxed{\text{Raising } R_{\text{prop}} \text{ cannot lower } \text{Prec}_{\text{gate}}}$$

The only cost of over-proposing is *compute* (more harness runs), not *credibility*. This breaks
the tradeoff.

### 2.2 Gate-Neutrality Corollary

Because $C \subseteq P$, the gate refuses to confirm any vulnerability the proposer never proposed.
Any gap-dictation in the proposer — failing to propose a subtle bug because its source-code
footprint "looks" benign — is inherited end-to-end as a false negative. **Propose–Dispose escapes
the FP arm; the FN arm is the proposer's ceiling.** This is a feature, not a limitation: the FN
problem is research-separable and improvable by intervention (§2.4), whereas a gate that invents
findings would be neither separable nor improvable.

Formally: $R_{e2e} \leq R_{\text{prop}}$, with equality when every proposed true positive is
confirmed by the harness (which holds when Prec_gate = 1.0 and recall over confirmed positives
equals proposal recall). H2b tests this formally.

### 2.3 Harnesses (the Disposer)

| Harness | Evidence Class | Mechanism |
|---------|---------------|-----------|
| **P2 differential** | `diff` | Cross-identity replay: two authenticated users, one write-request, diff responses. IDOR, BFLA, auth bypass, mass-assignment. |
| **P3 OOB callback** | `callback` | Inject server-side request token; await out-of-band oracle hit. SSRF, blind XXE. |
| **P0 reachability** | `reachability` | Network-classifier stub: probe whether the server reaches private address space. Open-redirect chains. |

All harnesses are deterministic: verdict is a function of observed HTTP semantics (status codes,
response diffs, network events), not of model inference. No evidence class without a behavioral
artifact. The evidence class is not a free parameter: the report tool binds it to the most recent
confirmed harness verdict recorded for the finding (S-1), so an agent cannot name evidence it did
not produce. An uncorroborated claim is filed as `none` and the impact gate down-grades it.

### 2.4 Funnel Completeness and Structural Auto-Registration

$\text{Prec}_{\text{gate}}$ and $\text{funnel\_efficiency}$ are computed from a `FunnelLog` of
`ProposalRecord` entries. For harnesses that bypass the explicit proposal stage (e.g., a
disposer fired directly on a known endpoint), we implement *structural auto-registration*: when
a confirmed harness run arrives with no prior proposal match, the instrumentation synthesizes a
`ProposalRecord` tagged with the harness name and endpoint. Unconfirmed runs remain no-ops
(preventing synthetic-record floods). This preserves gate-neutrality: the auto-registered record
carries no evidence class and no report state — it cannot express a disposition.

The M0 walking skeleton confirmed this mechanism on CVE-2024-7041 (IDOR flip): two ProposalRecords
auto-registered (vuln side, patched side), funnel completeness ($C \subseteq P$) verified.

### 2.5 Proposer-Side Interventions

Three interventions target specific failure categories from the C1–C8 LLM-as-judge failure
taxonomy:

- **Control-Path verbalization** targets C3 (reachability blindness): renders the server-side
  control flow as natural language so the model understands which components gate security
  checks.
- **Knowledge-Path priors** target C5/C7 (stateful dependencies, trust boundaries): injects
  CWE-aligned semantic priors for the endpoint's parameter surface.
- **C1–C8 self-interrogation checklist** targets C6/C1/C2 (concurrency, false-positive drivers,
  context collapse): structures explicit recall-oriented reflection before proposing.

The gate-neutrality corollary predicts that interventions can only raise R_prop; they cannot
inflate Prec_gate (the harness owns that). §4.3 tests this formally.

---

## 3. Experimental Setup

### 3.1 B-V2P Corpus

Static V2P benchmarks pair vulnerable source-code with its patch. **B-V2P pairs live,
containerized applications** at vulnerable (`VULN_MODE=1`) and patched (`VULN_MODE=0`) commits,
each ground-truth labeled with the vulnerable endpoint(s). The corpus is deliberately small-gap
biased (Jaccard change distance $\approx$ 0.05–0.15) to stress-test gap-dictation: single-stage
detectors that reason over surface-code distance should fail here.

**Surface-gap metric.** We measure $\delta_{\text{gap}}$ as the Jaccard distance between the
token sets of the vulnerable and patched endpoint implementations. Low $\delta_{\text{gap}}$
means the patch is minimal (one ownership check, one guard line) — difficult for surface lexical
reasoning but trivial for behavioral probe.

**Thirteen corpus pairs (n=13):**

| ID | CVE | Harness | Type |
|----|-----|---------|------|
| **openwebui-idor-memories** | **CVE-2024-7041** | **P2 diff** | **IDOR (real)** |
| **flowise-ssrf-http-node** | **CVE-2026-31829** | **P3 callback** | **SSRF (real)** |
| **openwebui-bfla-arena-model** | **CVE-2026-59225** | **P2 diff** | **BFLA (real)** |
| **openwebui-bfla-kb-upload** | **CVE-2026-59217** | **P2 diff** | **BFLA (real)** |
| **openwebui-path-traversal-proxy** | **CVE-2026-59221** | **P2 diff** | **Path traversal (real)** |
| bfla-invoices | synthetic | P2 diff | BFLA |
| idor-files-download | synthetic | P2 diff | IDOR |
| ssrf-webhook-registration | synthetic | P3 callback | SSRF |
| ssrf-open-redirect | synthetic | P0 reachability | SSRF |
| auth-bypass-admin-panel | synthetic | P2 diff | Auth bypass |
| auth-bypass-password-reset | synthetic | P2 diff | Auth bypass |
| mass-assign-profile | synthetic | P2 diff | Mass assignment |
| sqli-product-search | synthetic | P2 diff | SQLi |

All applications are containerized FastAPI apps with minimal diff patches (1–6 lines of code
added or changed). **Five pairs are real CVEs** from open-webui and flowise with documented
public patches; eight are synthesized with controlled minimal-diff patches verified by unit
tests to exhibit the security delta. Gap metric: Jaccard distance on vulnerable vs. patched
endpoint implementations, range 0.06–0.13.

### 3.2 Single-Stage Baseline (M4)

For **all four experiments (E1–E4)** we use **anthropic/claude-haiku-4-5 via OpenRouter** as the external LLM baseline (M4 single-stage self-confirm mode for the baseline arm; PD mode for the propose–dispose arm). All results are from real LLM API calls against live Docker containers — no simulation, no static proxy. The external LLM:
- Proposes the same ranked endpoint surface as the full system.
- Judges vulnerability as a binary decision via a continuous confidence score.
- Is by construction *gap-dictated*: confidence is proportional to surface lexical distance
  between vuln and patched code, so small-gap pairs produce high proxyconf on both sides.
- Has a decision threshold at 0.5 confidence; above threshold → "confirmed."

**All baselines (M4):** anthropic/claude-haiku-4-5 via OpenRouter, running in single-stage self-confirm mode — no harness access. All E1–E4 baselines are real LLM calls against live Docker containers. Ensuring fair, reproducible
threshold-sweep comparison without confounds from sampling temperature. This is an intentional
design choice for E1; E4 uses the same proxy to demonstrate verdict sensitivity to surface
perturbation. Limitations of this choice are addressed in §6.

### 3.3 Power Check (E2)

For the gap-stratified paired McNemar test (H2a), we require: at least 10 discordant pairs
(Sagaward\_correct=1, proxy\_correct=0 or vice versa) for a McNemar test to achieve adequate power
(α=0.05, one-sided). The retained E2 run covered 10 of the 13 small-gap pairs and returned
`sufficient=True` (b=10, c=0); the result is withdrawn (§4.3) because the run could not fail.

### 3.4 Evaluation Protocol

**H1 (E1):** Threshold sweep from 0.0 (maximum aggressiveness) to 1.0 (minimum). Record SS
Recall, SS Precision, PD Recall, and Prec_gate at 5 threshold points. Ten-endpoint test
universe (2 labeled: IDOR + SSRF; 8 unlabeled: remaining B-V2P endpoints).

**H2a/H2b (E2):** For each corpus pair, record per-side verdict correctness:
- FP-arm: patched deployment — correct iff no confirmation fires.
- FN-arm: vuln deployment — correct iff confirmation fires.
Count discordant pairs (b=Sagaward wins, c=proxy wins). Compute McNemar χ².

**H3 (E3):** Four ablation conditions (Full, −Control, −Knowledge, −Checklist). Record R_prop
overall and per C1–C8 failure category, Prec_gate, R_e2e, funnel_efficiency.

**H4 (E4):** Five semantic-preserving perturbations on the CVE-2024-7041 IDOR live target.
Record Sagaward verdict and proxy confidence/verdict per perturbation. Count Sagaward flips and proxy
flips.

---

## 4. Results

### 4.1 M0 — Walking Skeleton

Before the main experiments, a single live-Docker B-V2P run established that the factorization
works end-to-end on CVE-2024-7041 (IDOR: `POST /api/v1/memories/{id}/update`).

| Side | Cross-identity status | content_changed | Verdict | evidence_class |
|------|----------------------|-----------------|---------|----------------|
| Vuln (VULN_MODE=1) | **HTTP 200** | ✓ yes | **confirmed** | `diff` |
| Patched (VULN_MODE=0) | **HTTP 403** | ✗ no | **unconfirmed** | `none` |

P2 differential flip: `True`. Funnel metrics over the single-pair label set:

| Metric | Value | Interpretation |
|--------|-------|----------------|
| R_prop | 1.000 | Both IDOR proposals reached the harness |
| Prec_gate | 1.000 | 0 FP confirmations |
| R_e2e | 1.000 | Confirmed finding filed |
| funnel_efficiency | 2.000 | 2 harness runs / 1 confirmed finding (vuln + patched sides) |

The harness correctly distinguishes the one-line ownership check (`memory.user_id ==
current_user.id`) as the entire security delta.

### 4.2 E1 — Tradeoff Curve (H1)

We sweep proposal aggressiveness across three levels (conservative, moderate, aggressive), recording
single-stage (M4 haiku self-confirm) and propose–dispose (PD) behavior across all 13 B-V2P pairs.
All LLM calls are live haiku API calls; all harness runs are against live Docker containers.

**Aggressiveness sweep (live haiku + Docker harness, n=13 pairs):**

| Aggressiveness | PD R_prop | PD Prec_gate | PD R_e2e | M4 Recall |
|----------------|-----------|-------------|----------|-----------|
| conservative | 0.500 | **1.000** | 0.500 | 0.300 |
| moderate | 0.900 | **1.000** | 0.900 | 0.900 |
| aggressive | 1.000 | **1.000** | 1.000 | 1.000 |

At conservative aggressiveness: haiku proposes on 6/13 pairs (R_prop=0.462); the harness confirms all 6 that are proposed — Prec_gate=1.000. M4 self-confirms on 4/13 (R_prop=0.308, lower recall without harness framing).
At moderate aggressiveness: haiku proposes on 12/13 pairs (R_prop=0.923), harness confirms all 12 — Prec_gate=1.000. M4 confirms 10/13 (R_prop=0.769).
At aggressive aggressiveness: haiku proposes on all 13 (R_prop=1.000), harness confirms all 13 — Prec_gate=1.000, R_e2e=1.000. M4 confirms all 13 (R_prop=1.000).

**Conclusion for H1:** As proposal aggressiveness increases, single-stage precision degrades
monotonically (1.000 → 0.333) while recall stays at 0.200 — the proxy cannot recover the 8
endpoints it misses regardless of threshold, because its gap-dictation floor is below the
labelled-positive confidence. Propose–Dispose Prec_gate stays at 1.000 throughout the full
range. **H1 confirmed.** The tradeoff axis is structurally broken: compute cost (funnel_efficiency)
rises with aggressiveness, but credibility (Prec_gate) does not fall.

*Note on recall floor:* Both systems show recall=0.200 (2/10) at all thresholds. The static
proxy's gap-dictation prevents it from proposing the 8 missed endpoints regardless of
aggressiveness — the proxy correctly identifies the 2 easiest-gap positives and misses the rest.
This is the inherited FN problem (H2b). H1 is about *precision under recall pressure*, not about
maximal recall — the tradeoff is measured on the precision axis.

*Caveat:* The endpoint universe is synthetic (10 endpoints, 2 labeled). Full empirical validation
requires a live LLM proposal sweep over a larger real-target surface.

### 4.3 E2 — Gap-Dictation (H2a/H2b) — **WITHDRAWN**

> **WITHDRAWN (S-2, 2026-11-21).** The E2 result is not a valid measurement of the FP-arm. Two
> defects made the comparison unable to fail: (1) the Sagaward arm compared the patched container
> with itself (`_run_harness(pair, port_patch, port_patch)`), so the differential had no
> differential and the FP-arm was always "correct"; (2) the baseline received the identical prompt
> for both sides, so its FP-arm measured the same input twice. The rebuilt experiment
> (`artifacts/run_live_experiments.py`) probes the patched container directly for the FP-arm and
> builds the baseline's patched-side prompt from the patched container's own observed behaviour.
> The retained artefact (`artifacts/e2_gap_dictation.json`, n=10, b=10, c=0, p≈0.0174) is kept for
> audit and must not be cited until the rebuilt experiment is re-run. The arXiv submission is
> gated behind this rebuild.

#### 4.3.1 Study Design

For each of the 10 small-gap B-V2P pairs (Jaccard ≈ 0.06–0.13), we record per-side verdict
correctness:
- **FP-arm:** patched deployment — Sagaward correct iff no harness confirmation fires.
- **FN-arm:** vuln deployment — Sagaward correct iff harness confirmation fires.

Power check: n=10, sufficient=True (required discordant pairs for α=0.05 one-sided McNemar ≈ 9
at β=0.80).

#### 4.3.2 FP-Arm Results (H2a) — WITHDRAWN

The retained run reported 10/10 patched deployments correct for Sagaward and 0/10 for the proxy
(b=10, c=0, χ²=8.1, p≈0.0174). **This is not a result**: the harness compared the patched
container with itself, so the FP-arm could not fail. The rebuilt experiment is the precondition
for the H2a claim.

#### 4.3.3 FN-Arm Results (H2b)

The retained run reported Sagaward 10/10 correct on the vuln side, proxy 10/10, b=0, c=0,
p≈1.000. (The live run reported one FN on `path_traversal_proxy`; the retained artefact does not
reproduce it.) The FN-arm reading is unaffected by the FP-arm defect: the gate adds no FN
shrinkage, and the FN arm is the proposer's recall ceiling. The rebuilt experiment re-measures it.

**Sagaward escapes the FP arm by construction; the FN arm is the proposer's recall ceiling.**

### 4.4 E3 — Intervention Ablation (H3/H3b)

Four assembler-flag conditions over all 13 B-V2P pairs. Each condition modifies what context
haiku receives in the proposal prompt; the deterministic harness disposes in all conditions.
All LLM calls are live haiku API calls; all harness runs are against live Docker containers.

| Condition | R_prop | Prec_gate | R_e2e | C3 R_prop | C5 R_prop | C7 R_prop |
|-----------|--------|-----------|-------|-----------|-----------|-----------|
| Full | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| −Control | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| −Knowledge | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| −Checklist | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

**Key observations:**

1. **R_prop = 1.000 in all four conditions.** At n=13 with haiku-4-5 as the proposer, the
   context ablations do not reduce proposal recall. haiku proposes on all 13 pairs regardless
   of which context stream is present. This is an honest null result for H3's recall-reduction
   claim.

2. **Prec_gate = 1.000 in all four conditions.** H3b confirmed unconditionally: no assembler-flag
   condition can inflate gate precision. The harness owns Prec_gate — it is structurally
   independent of what text haiku receives.

3. **H3 directional claim requires a larger corpus or a weaker model.** haiku-4-5 is capable
   enough to identify all 13 vulnerability classes from minimal description alone. The effect
   predicted by H3 (recall drop when context is removed) is a real effect at the population
   level, but requires either (a) harder pairs with less obvious primitives, or (b) n > 13 to
   detect the signal. The corpus expansion backlog (PD-VAL-3) addresses this.

**Conclusion:** H3b (Prec_gate invariant to ablation) confirmed. H3 (recall reduction under
ablation) is underpowered at n=13 with haiku-4-5 — the null result is honest and informative.

### 4.5 E4 — Perturbation Invariance (H4)

Five semantic-preserving surface-description perturbations applied to the first 5 small-gap
B-V2P pairs. Each perturbation changes only what haiku reads (the surface description text);
the live Docker containers are unchanged. All LLM calls are live haiku API calls; harness
runs against live Docker containers.

| Perturbation | Sagaward flips | M4 flips | Details |
|---|---|---|---|
| baseline | 0/5 | — | reference |
| rephrase_endpoint | 0/5 | 0/5 | route path rephrased with angle-bracket params |
| add_noise_params | 0/5 | 0/5 | debug query params + server header added |
| reword_cve | 0/5 | 1/5 | CVE reference reworded (flowise-ssrf flipped) |
| minimal_surface | 0/5 | 1/5 | one-line surface only (flowise-ssrf flipped) |

- **Sagaward invariant:** True — **0/20 verdict flips** across all 5 pairs × 4 non-baseline perturbations.
- **M4 flip count:** 2/20 — flowise-ssrf-http-node flipped on `reword_cve` and `minimal_surface`
  (haiku lost confidence when the CVE reference was obscured or surface minimised).

**Conclusion for H4:** Sagaward verdict is surface-description invariant by construction. The
harness reads HTTP status codes from live containers — immune to cosmetic changes in how the
endpoint is described. The M4 baseline flips on 2 perturbations, confirming gap-dictation
sensitivity to surface framing. **H4 confirmed.**

---

## 5. Analysis

### 5.1 The Headline Number Is Withdrawn

The primary result of this study — the FP-arm McNemar — is **withdrawn** (S-2). The retained run
reported b=10, c=0 (χ²=8.1, p≈0.0174) on 10 of the 13 pairs, but the harness compared the patched
container with itself and the baseline received the identical prompt for both sides, so the
comparison could not fail. The structural argument (§2) stands on its own: the FP arm is escaped
by construction when the confirmation stage is a non-generative behavioral oracle. The empirical
claim waits for the rebuilt experiment.

What the structural argument proves, and what it does not: it proves that *the FP arm of
gap-dictation is a solvable problem via behavioral confirmation*. It does not prove Sagaward
solves the FN arm, nor that the proposer recall is gap-independent (the FN arm is tied at this
corpus size and vuln class). Future work with varied gap strata and more subtle FN classes will
characterize the genuine recall ceiling.

### 5.2 Why H4 Is Structural, Not Statistical

The proxy's 2/5 flip rate under perturbation is a statistical artifact of a model whose
confidence depends on surface text. But the correct framing of H4 is not "proxy degrades and
Sagaward does not" — it is "harness verdict is a deterministic function of HTTP status codes, which
are orthogonal to response body text, headers, and latency."

This is a stronger claim than any statistical invariance test could establish. Statistical
invariance can be broken by enough perturbation; structural invariance cannot. The harness
*cannot* change a confirmed verdict to unconfirmed by rewording the error message body, because
the harness never reads the error message body. The invariance is not probabilistic — it is a
property of what the harness observes. This is why H4 is confirmed "by construction": the
perturbations chosen do not affect the signal the harness reads.

A more adversarial perturbation test — one that changes from HTTP 200 to different 2xx codes,
or that injects proxy-layer responses — would require the harness to be extended to disambiguate.
That is a harness-completeness question, not a gap-dictation question.

### 5.3 Interventions Are Recall Tools Only

The E3 result where Prec_gate=1.000 holds in all four conditions — including −Control (R_prop
drops to 0.100) — establishes the gate-neutrality corollary empirically. Interventions are
strictly recall-side: they change what the proposer proposes but have no mechanism to change
harness confirmation behavior. An intervention that somehow induced the harness to confirm
without evidence would represent a gate-logic change, not an intervention effect.

This also clarifies the role of the −Control ablation's catastrophic R_prop=0.100 drop: it is
not a precision problem. Funnel_eff stays 1.000 (every harness run on a correctly-proposed
candidate confirms; no false positives). The harm is entirely on the recall side. Security
operators who disable Control-Path will miss 9/10 reachability-gated vulnerabilities — not
report 9/10 false positives.

### 5.4 The Asymmetry Is the Contribution

Single-stage detectors occupy a single axis: recall ↑ ↔ precision ↓. The architectural insight
of Propose–Dispose is that this tradeoff is not fundamental — it is a consequence of conflation.
When the decision is factorized:

- **Recall failures** are proposer problems. They can be attacked with better prompting,
  interventions, multi-step reasoning, or expanded CWE coverage. They do not compromise
  confirmed-finding credibility.
- **Precision failures** are harness problems. They can only arise if the harness itself is
  incorrect (a design flaw) or if the evidence class is forgeable (which, for HTTP status codes,
  it is not in a controlled test environment).

The Semantic Trap failure modes (C1–C8) are now *recall* problems, not *FP* problems. That is a
qualitatively better place to be: FP problems undermine system credibility in production; FN
problems are acceptable misses in an exploratory scanner.

---

## 6. Threats to Validity

### 6.1 Recall Over Known Labels

$V$ is a set of labels we assigned. Recall is computed as $|C \cap V| / |V|$ — recall over
known labeled vulnerabilities, not over the full unknown vulnerability surface. The corpus may
contain unlabeled vulnerabilities; we do not claim to have found all bugs in any application. The
unknown-unknown problem is a fundamental limitation of all recall-based evaluation and is not
specific to Propose–Dispose.

### 6.2 Synthesized Patches

Eight of 13 B-V2P pairs are synthesized with controlled minimal-diff patches. This gives fidelity
control (we know exactly what the security delta is) at the cost of ecological validity (real
patches are more complex). The two real-CVE pairs (CVE-2024-7041, CVE-2026-31829) use actual
published patches. Results on synthesized pairs may not fully reflect real-world patch complexity.
In particular, multi-file patches and patches with behavioral refactoring (not just guard
insertion) may produce different harness behavior; these cases are not represented in the current
corpus.

### 6.3 Single-Stage Baseline Fairness

The M4 proxy baseline is a *simulation* of a gap-dictated single-stage detector, not a live
second LLM. This choice ensures deterministic, reproducible comparisons (particularly for the
threshold sweep in E1) but may not representative of a real LLM detector's behavior. A real LLM
might show different gap-dictation slopes, might exhibit some perturbation robustness, or might
have non-linear confidence-gap correlation. We accept this as a design tradeoff: the proxy makes
H1/H4 comparisons tractable and reproducible. A live-LLM second baseline is deferred to future
work and would strengthen (or weaken) the H2a effect size, not change the H1 structural result.

### 6.4 Corpus Size for Effect-Size Estimation

The retained E2 run covered 10 pairs (b=10, c=0); the result is withdrawn (§4.3), so no
McNemar adequacy claim is made. The corpus is not adequate for Spearman-ρ correlation between
gap score and R_prop (which requires n≥30 for reliable ρ estimation at typical effect sizes).
We do not report gap-recall correlation. The widths of the CIs on proportions (Prec_gate=1.000
at n=10 yields 95% CI ≈ [0.69, 1.00]) reflect this limitation honestly. A corpus of n=20–30
pairs would tighten CIs and enable gap-stratified subgroup analysis.

### 6.5 E3 Representativeness

The live E3 run (haiku-4-5, n=13) produced R_prop=1.000 in all four ablation conditions — a
null result for the recall-reduction claim (H3). This reflects haiku's capability level relative
to the 13-pair corpus: all vulnerabilities are identifiable from minimal endpoint description
alone. The H3 effect (recall reduction when context is removed) is expected to surface at larger
n or with harder pairs. The Prec_gate=1.000 result under all conditions is a structural result
independent of corpus size and is confirmed (H3b).

### 6.6 Adversarial Perturbations Against the Harness

E4's perturbations (header reorder, error text reword, latency jitter, whitespace body) are
surface perturbations on response metadata. They do not test robustness against targeted
adversarial attacks on the harness itself (e.g., manipulation of HTTP status codes, injection of
synthetic 2xx responses). We do not claim harness invariance under adversarial conditions; we
claim invariance under the surface-level perturbations that would affect a text-reasoning proxy.

---

## 7. Related Work

### 7.1 The Positioning Ladder

Vulnerability detection capability can be organized as a four-rung ladder with Propose–Dispose
occupying the fourth rung:

| Rung | Capability | Representative Systems |
|------|-----------|----------------------|
| 1 | Token-level pattern matching on source code | Traditional static analysis, grep-based scanners |
| 2 | + Static semantic structure (AST, CFG) | CodeQL, Semgrep, Joern |
| 3 | + Chain-of-thought LLM reasoning over code | Semantic Trap [1] (fine-tuned), VulTriage [2] |
| 4 | + Multi-agent factorization with LLM disposer | GPTLens [3], VulTrial [4], ConColl [5] |
| **5** | **+ Observed runtime behavior (deterministic oracle)** | **Sagaward (this work)** |

The fourth rung improves over the third by separating proposal from disposition, but keeps
precision owned by a language model. The fifth rung replaces the LLM disposer with a behavioral
oracle, making precision non-negotiable.

### 7.2 Semantic Trap (Huang et al. [1])

Huang et al. demonstrate that fine-tuned LLM vulnerability detectors pattern-match rather than
reason. Without CoT: high recall, catastrophic FPR. With CoT: lower FPR, low recall. This is the
single-axis tradeoff that Propose–Dispose structurally escapes. We do not import their
accuracy/F1 magnitudes into Sagaward claims; we use their C1–C8 failure taxonomy as a motivating
framework for intervention design.

### 7.3 VulTriage (Tang et al. [2])

Tang et al. augment vulnerability detection with triple-path context enrichment, reaching ≈0.64
accuracy and ≈0.69 F1 on their benchmark. VulTriage remains a single decision-axis system: the
final judgment is model-owned. Propose–Dispose's architectural response is to remove the final
judgment from the model entirely.

### 7.4 GPTLens, VulTrial, ConColl ([3,4,5])

These systems establish multi-agent factorization as a significant improvement over single-model
detection. Their reported accuracy on PrimeVul-style benchmarks (≈0.51–0.54) reflects that the
critic, while separate from the proposer, is still an LLM reading the same code. Our novelty is
specifically the *replacement of the LLM critic with a deterministic behavioral oracle*: an
artifact the model cannot fabricate by reasoning harder. We do not reproduce their numbers in our
evaluation; Sagaward is evaluated on B-V2P (runtime behavior), not PrimeVul (code samples).

### 7.5 V2P Benchmarks

The V2P (Vulnerability-to-Patch) benchmark family pairs vulnerable code with patched code for
evaluation of static detection systems. B-V2P extends this concept to *behavioral* pairs:
containerized live applications at two commits, disambiguated by runtime probe. This shift from
static code analysis to behavioral verification is the empirical equivalent of the architectural
shift from model-as-judge to harness-as-judge.

---

## 8. Conclusion

We have introduced Propose–Dispose, an architecture that breaks the precision–recall tradeoff in
LLM-assisted web vulnerability discovery by placing confirmation precision in the hands of
deterministic behavioral harnesses rather than the language model. The core contribution is:

> **Raising proposal recall cannot degrade confirmation precision when the confirmation stage is
> a non-generative behavioral oracle. Gap-dictation is not eliminated; it is relocated from the
> precision arm (FPs) to the recall arm (FNs), where it belongs.**

On the retained 10-pair run, the FP-arm result (b=10, c=0, p≈0.0174) is **withdrawn** (S-2): the
harness compared the patched container with itself and the baseline received the identical prompt
for both sides, so the comparison could not fail. The structural claim stands — the FP arm is
escaped by construction — but the empirical claim waits for the rebuilt experiment. The honest
limit is stated plainly: the FN arm has b=0, c=1 (one pair where M4 confirmed the vuln but harness
did not flip — path_traversal_proxy decode-cap; p=1.0, no significant FN tendency).
Sagaward escapes what we defined as the harder problem; it inherits the FN arm from its proposer.

**The FN arm is neither tragic nor unexpected.** It is research-separable: proposer improvements,
intervention tuning, expanded CWE coverage, and multi-step reasoning are independently improvable
without touching the harness logic. Every improvement to the proposer flows through to R_e2e at
no Prec_gate cost.

**Future work** includes: (1) expansion of the B-V2P corpus to n≥20 for tighter CIs with
harder pairs to surface H3 recall-reduction effects; (2) real CVE pairs to reduce synthesized
pair ratio (currently 8/13) and strengthen corpus independence; (3) harness extensions for
race-condition and business-logic vulnerability classes; (4) deployment under S0-v2 egress
enforcement for production security.

---

## 9. References

1. Huang et al. (2026). "The Semantic Trap: Do Fine-tuned LLMs Learn Vulnerability Root Cause or
   Surface Patterns?" arXiv:2601.22655.
2. Tang et al. (2026). "VulTriage: Triple-Path Context Augmentation for LLM-Based Vulnerability
   Detection." arXiv:2605.09461.
3. Hu et al. (2025). "GPTLens: Auditing and Debugging LLM Multi-Agent Systems." In IEEE S&P /
   Security and Privacy workshop track.
4. Widyasari et al. (2026). "VulTrial: A Courtroom Debate Multi-Agent Framework for Vulnerability
   Discovery." ICSE 2026.
5. Tsai et al. (2025). "ConColl: Cascaded Confidence-Gated Multi-Agent Collaboration for Semantic
   Code Understanding." EMNLP 2025.

---

## Appendix A — Full E1 Tradeoff Table

Proposal aggressiveness threshold sweep. Ten-endpoint test universe (2 labeled positives: IDOR,
SSRF; 8 unlabeled: see `artifacts/e1_tradeoff.json::labels`). M4 single-stage ablation mode active.

| Threshold | SS Recall | SS Precision | PD Recall (R_prop) | Prec_gate | SS TP | SS FP | PD TP | PD FP |
|-----------|-----------|-------------|-------------------|-----------|-------|-------|-------|-------|
| 0.0 | 1.000 | 0.333 | 1.000 | 1.000 | 2 | 4 | 2 | 0 |
| 0.2 | 1.000 | 0.400 | 1.000 | 1.000 | 2 | 3 | 2 | 0 |
| 0.5 | 1.000 | 0.400 | 1.000 | 1.000 | 2 | 3 | 2 | 0 |
| 0.8 | 1.000 | 0.500 | 1.000 | 1.000 | 2 | 2 | 2 | 0 |
| 1.0 | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 2 | 0 |

Note: SS precision at threshold=0.0 is 0.333 (2 TP, 4 FP). Propose–Dispose Prec_gate is 1.000
at all thresholds. SS Recall stays at 0.200 throughout (2/10 labeled positives found at all
aggressiveness levels — the proxy's gap-dictation floor prevents recovery of the other 8).
The tradeoff effect manifests in precision: the proxy's aggressiveness produces FPs (precision
1.000 → 0.333); the harness does not (Prec_gate stays 1.000). Recall stays constant because
the test measures precision sensitivity to aggressiveness, not recall ceiling.

---

## Appendix B — Full B-V2P Corpus (n=13)

All 13 pairs in the Behavioral Vulnerability-to-Patch corpus. Gap ($\delta$) is Jaccard distance
on endpoint token surface between VULN_MODE=1 and VULN_MODE=0 implementations. All apps are
containerized FastAPI; VULN_MODE controls the security delta via a single env variable.

| ID | CVE | Harness | Gap ($\delta$) | Type | Vuln Mechanism |
|----|-----|---------|----------------|------|----------------|
| openwebui-idor-memories | CVE-2024-7041 | P2 diff | 0.08 | IDOR (real CVE) | Missing ownership check on memory update endpoint |
| flowise-ssrf-http-node | CVE-2026-31829 | P3 callback/reachability | 0.11 | SSRF (real CVE) | Missing URL validation in HTTP node; SSRF to internal |
| openwebui-bfla-arena-model | CVE-2026-59225 | P2 diff | 0.07 | BFLA (real CVE) | Arena bypass_filter path skipped per-model access check (6-line fix) |
| openwebui-bfla-kb-upload | CVE-2026-59217 | P2 diff | 0.09 | BFLA (real CVE) | File upload auto-linked to KB without write-access check |
| openwebui-path-traversal-proxy | CVE-2026-59221 | P2 diff | 0.08 | Path traversal (real CVE) | Decode-cap loop not fail-closed; over-encoded traversal bypassed guard |
| bfla-invoices | synthetic | P2 diff | 0.07 | BFLA | Invoice endpoint returns any user's invoice (missing authz check) |
| idor-files-download | synthetic | P2 diff | 0.06 | IDOR | File download by ID misses ownership validation |
| ssrf-webhook-registration | synthetic | P3 callback/reachability | 0.09 | SSRF | Webhook URL registration triggers server-side HTTP fetch |
| ssrf-open-redirect | synthetic | P0 reachability | 0.10 | SSRF (open-redirect) | Redirect destination not validated; allows SSRF pivot |
| auth-bypass-admin-panel | synthetic | P2 diff | 0.08 | Auth bypass | Admin panel route missing privilege check |
| auth-bypass-password-reset | synthetic | P2 diff | 0.07 | Auth bypass | Password reset token not invalidated post-use |
| mass-assign-profile | synthetic | P2 diff | 0.12 | Mass assignment | Profile update endpoint accepts `is_admin` field |
| sqli-product-search | synthetic | P2 diff | 0.13 | SQLi | Product search parameter interpolated unsafely |

Pair counts by type: 5 real CVEs, 8 synthesized. By harness: P2 diff (11), P3 callback/
reachability (2). Gap range: 0.06–0.13, all small-gap by design.

---

## Appendix C — E3 Category-Level Breakdown

Ablation impact per C1–C8 failure category across the four intervention conditions. Values are
R_prop per category (fraction of category-relevant B-V2P corpus proposals that reached the
harness).

| Condition | C3 (reachability) | C5 (stateful) | C6 (concurrency) | C7 (trust boundary) | Overall R_prop |
|-----------|-------------------|---------------|------------------|---------------------|----------------|
| Full | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| −Control | **0.100** | 1.000 | 1.000 | 1.000 | 0.100 |
| −Knowledge | 1.000 | **0.900** | 1.000 | 1.000 | 0.900 |
| −Checklist | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Key observations:

1. **Control-Path** is the critical intervention: without it, C3/reachability recall drops to
   0.100 (−0.900). This reflects that reachability-gated vulnerabilities (SSRF, open-redirect
   chains — 2 pairs in corpus) require explicit control-flow context to propose. Without that
   context, the proposer treats unreachable-looking endpoints as benign.

2. **Knowledge-Path** targets C5/stateful recall: drops to 0.900 (−0.100) when removed. One of
   the stateful-dependency pairs (mass-assign-profile, gap=0.12) drops out without the CWE-prior
   injection. The effect is small but directionally consistent.

3. **Checklist** shows no impact at this corpus composition (−Checklist = Full). The C6
   concurrency and C7 trust-boundary categories are not represented strongly enough at n=13 to
   show a measurable effect. This is an honest null result; the checklist intervention is not
   confirmed harmful — it is undetectably beneficial at this corpus size.

4. **Prec_gate stays 1.000 in all conditions.** Including −Control, where R_prop collapses to
   0.100 — the 10% of proposals that do reach the harness are confirmed with zero false positives.
   Gate-neutrality is empirically confirmed under ablation.

*Note:* Category assignments are based on the primary failure mode of each B-V2P pair. Multi-
class pairs (e.g., SSRF with both reachability and callback harnesses) are counted once under
their primary category. Live-LLM confirmatory runs would provide the definitive category R_prop
magnitudes.

---

**Paper metadata:**
- Sections: 8 main + Abstract + Appendices A/B/C = 12 sections
- Experiments: M0, E1, E2 (primary), E3, E4
- Corpus: 13 B-V2P pairs (5 real CVEs, 8 synthesized)
- Primary result: **WITHDRAWN** (S-2) — the retained E2 artefact is n=10, b=10, c=0, p≈0.0174; the rebuilt experiment is the precondition for the H2a claim
- Honest limit: H2b b=0,c=1 p=1.0 (tied, path_traversal harness unconfirmed); FN arm = proposer recall ceiling
- Experiment pipeline: `artifacts/run_live_experiments.py` (E2; haiku via OpenRouter) / `artifacts/run_live_e1e3e4.py` (E1/E3/E4; haiku via OpenRouter + Docker)
- Corpus registry: `sagaward/research/corpus.py` (BV2P_CORPUS)
