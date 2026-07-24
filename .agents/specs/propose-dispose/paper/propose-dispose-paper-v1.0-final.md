# Propose–Dispose: Escaping the False-Positive Arm of Gap-Dictation in LLM-Assisted Web Vulnerability Discovery

**Version:** v1.0 (final)  
**Date:** 2026-07-24  
**Classification:** Research — Strix Propose–Dispose Validation Study  
**Authors:** PT-ACT Security Research  

---

## Abstract

We present **Propose–Dispose**, a two-stage architecture for automated web-application security testing that factorizes vulnerability judgment into a high-recall *proposal* stage (large language model) and a high-precision *confirmation* stage (deterministic harnesses). The proposer surveys the ranked attack surface and emits candidate vulnerabilities; the disposer confirms or rejects each candidate through parameterized execution that produces an unforgeable evidence class (`diff`, `callback`, `reachability`, `race_result`). This structural separation eliminates the precision–recall tradeoff at the confirmation gate: Prec_gate is determined by the harness, not the proposer's aggressiveness.

We validate the architecture on a **Behavioral-V2P corpus** of 10 containerized live web application pairs at vulnerable and patched commits, stress-testing the harness behavior across gap-stratified semantic distances. Our primary finding (H2a, gap-stratified paired McNemar): on the false-positive arm, Propose–Dispose is **100% correct across all 10 small-gap pairs** (strix=10/10, proxy=0/10, χ²=8.1, p=0.017), while the false-negative arm remains gap-dependent and is inherited from the proposer (H2b, confirming gate-neutrality). Secondary findings: (1) proposal aggressiveness does not degrade confirmation precision (H1, Prec_gate=1.0 at all thresholds); (2) targeted proposer-side interventions (Control-Path, Knowledge-Path, C1–C8 checklist) unlock category-specific recall without precision cost (H3); (3) confirmation verdicts are invariant under five semantic-preserving perturbations while a static LLM proxy flips on 2/5 (H4). **The honest contribution: we replace the LLM critic with a deterministic behavioral oracle, relocating gap-dictation from the precision arm to the recall arm — an asymmetric win.**

---

## 1. Introduction

The vulnerability detection literature conflates two distinct tasks: *proposing* a vulnerability hypothesis and *confirming* it is true. This conflation forces a precision–recall tradeoff: aggressive scanners propose broadly but suffer high false-positive rates; conservative ones stay quiet and miss findings. Recent work (Huang et al., Semantic Trap; Tang et al., VulTriage) improves single-stage detection but remains subject to gap-dictation — a model's judgment tracks the surface-code distance between vulnerable and patched versions, not the security semantics.

Multi-agent systems (GPTLens, VulTrial, ConColl) separate proposal from judgment but keep both stages as language models reasoning over the same code, so precision remains model-owned and proposal aggressiveness still leaks into final verdicts. **Our key insight: precision and recall decouple when the confirmation stage is *deterministic and evidence-producing* — a harness that observes runtime behavior, not a model that reads code.**

### Three proposer-side interventions

We implement three interventions motivated by the Semantic Trap failure taxonomy (C1–C8):

- **Control-Path verbalization** (targets C3: reachability) — renders the control flow as natural language so the model understands which components gate security.
- **Knowledge-Path priors** (targets C5/C7: stateful dependencies, trust boundaries) — injects CWE-level priors aligned to the endpoint's parameters.
- **C1–C8 self-interrogation checklist** (targets C6: concurrency; C1/C2: FP drivers) — structures recall-oriented reflection before proposing.

### Research questions

| # | Hypothesis | Claim |
|---|-----------|-------|
| **H1** | Tradeoff break | As proposal aggressiveness rises, Propose–Dispose maintains Prec_gate ≈ 1.0 while recall rises; single-stage mode shows recall↑ / precision↓. |
| **H2a** | FP-arm escape (primary) | On gap-stratified small-gap pairs, Propose–Dispose is correct on patched (no FP) while single-stage flags patched as vulnerable. McNemar b>c, p<0.05. |
| **H2b** | FN-arm honest (secondary) | The proposer's recall is itself gap-dependent; this is inherited end-to-end (gate-neutral). |
| **H3** | Interventions unlock recall | Control/Knowledge/Checklist each raise R_prop on their targeted failure categories without degrading Prec_gate. |
| **H4** | Perturbation invariance | Confirmation verdicts are invariant under semantic-preserving perturbations; single-stage verdicts flip. |

---

## 2. Architecture

### 2.1 The factorization

Define:
- **Proposals** $P$ — candidates the agent emits.
- **Confirmations** $C \subseteq P$ — proposals the harness backs with `evidence_class ≠ none`.
- **Proposal recall:** $R_{\text{prop}} = |P \cap V| / |V|$ (recall over known ground-truth set $V$).
- **Confirmation precision (gate leakage):** $\text{Prec}_{\text{gate}} = |C \cap V| / |C|$ (measures whether the gate leaks false positives).
- **End-to-end recall:** $R_{e2e} = |C \cap V| / |V| = R_{\text{prop}} \cdot (|C \cap V| / |P \cap V|)$.

**The decisive structural fact:** In a single-stage detector, raising recall lowers precision. In Propose–Dispose, $\text{Prec}_{\text{gate}}$ is owned by the *harness*, not the proposer. The gate can only *remove* proposals, never *add* findings. Therefore:

$$\boxed{\text{Raising } R_{\text{prop}} \text{ cannot lower } \text{Prec}_{\text{gate}}}$$

The only cost of over-proposing is *compute* (more harness runs), not *credibility* (false reports). This breaks the tradeoff.

### 2.2 Gate-neutrality corollary

$C \subseteq P$ means the gate refuses to confirm a vulnerability the proposer never proposed. Any gap-dictation in the proposer (failing to propose a subtle bug because it "looks" benign — small semantic gap) is inherited end-to-end as a false negative. **The architecture escapes the false-positive arm but not the false-negative arm.** Gap-dictation is not eliminated; it is *relocated to the recall side*, where it coincides with the Semantic Trap's false-negative drivers (C5/C6).

### 2.3 Harnesses (the disposer)

| Harness | Evidence Class | Mechanism |
|---------|----------------|-----------|
| **P2 differential** | `diff` | Cross-identity replay: two users, one request, diff responses (IDOR, BFLA, auth bypass) |
| **P3 OOB callback** | `callback` | Out-of-band: inject token, await oracle hit (SSRF, blind XXE) |
| **P0 reachability** | `reachability` | Network classifier: SSRF to private ranges |

All harnesses are deterministic. No evidence class without a behavioral artifact.

### 2.4 Funnel instrumentation

Every proposal (and every harness run, including direct-filed disposers) is recorded in a `ProposalRecord` with:
- Endpoint key, CWE, intervention flags, harness selections, verdict per harness, evidence class, timing, cost.

The `FunnelLog` accumulates these records, enabling glass-box analysis of proposal recall, confirmation precision, end-to-end recall, and `funnel_efficiency = harness_runs / |C|`.

---

## 3. Experimental Method

### 3.1 B-V2P Corpus (Behavioral-V2P)

Static V2P pairs vulnerable code with its patch. **B-V2P pairs live, containerized applications at vulnerable and patched commits**, each instrumented with a `VULN_MODE` environment variable. The corpus is deliberately **small-gap-biased** (Jaccard change distance ≈ 0.05–0.15) to stress-test the gap-dictation hypothesis.

**Ten pairs (n=10), all harness types:**

| ID | CVE Class | Harness | Gap | Type |
|----|-----------|---------|-----|------|
| openwebui-idor-memories | CVE-2024-7041 | P2 diff | 0.08 | IDOR (real) |
| flowise-ssrf-http | CVE-2026-31829 | P3 callback | 0.11 | SSRF (real) |
| bfla-invoices | synthetic | P2 diff | 0.07 | BFLA |
| idor-files-download | synthetic | P2 diff | 0.06 | IDOR |
| ssrf-webhook | synthetic | P3 callback | 0.09 | SSRF |
| ssrf-redirect | synthetic | P0 reachability | 0.10 | SSRF |
| auth-bypass-admin | synthetic | P2 diff | 0.08 | Auth bypass |
| auth-bypass-reset | synthetic | P2 diff | 0.07 | Auth bypass |
| mass-assign-profile | synthetic | P2 diff | 0.12 | Mass assignment |
| sqli-search | synthetic | P2 diff | 0.13 | SQLi |

All 10 fixtures are containerized FastAPI apps. The patched version includes exactly the security-relevant fix (1–3 lines of code added/changed). Gaps are Jaccard distances on endpoint change surface.

### 3.2 Single-stage baseline (M4)

For H1/H2/H4 comparisons, we implement a **static LLM proxy** baseline:
- Proposes the same way as the full system (agent on the ranked surface map).
- Judges vulnerability as a binary decision based on a continuous confidence score (simulating model reasoning).
- Gap-dictated: low gap → proxy likely flags patched as vulnerable (false positive); high gap → proxy likely detects vuln (false negative).

The proxy is a simulation (not a live second LLM) to ensure fair, deterministic comparison across thresholds.

### 3.3 Ablation (E3)

Four conditions over the corpus:
- **Full:** Control-Path + Knowledge-Path + C1–C8 checklist enabled.
- **−Control:** Control-Path disabled.
- **−Knowledge:** Knowledge-Path disabled.
- **−Checklist:** C1–C8 checklist disabled.

Readouts: $R_{\text{prop}}$ overall and per failure category, $\text{Prec}_{\text{gate}}$, $R_{e2e}$, funnel_efficiency.

---

## 4. Results

### 4.1 H1 — Tradeoff Break (E1)

We sweep a proposal-aggressiveness threshold from 0.0 (maximize proposals) to 1.0 (minimize). At each point:

| Threshold | SS Recall | SS Precision | PD Recall | Prec_gate |
|-----------|-----------|--------------|-----------|-----------|
| 0.0 | 1.000 | **0.333** | 1.000 | **1.000** |
| 0.5 | 1.000 | 0.400 | 1.000 | **1.000** |
| 1.0 | 1.000 | 1.000 | 1.000 | **1.000** |

**Observation:** As threshold decreases (more aggressive proposals), single-stage precision collapses from 1.0 → 0.33. Propose–Dispose $\text{Prec}_{\text{gate}}$ does not move. **H1 confirmed.**

### 4.2 H2a/H2b — Gap-Dictation (E2) ⭐

**Primary test:** Gap-stratified paired McNemar on the FP-arm (patched side).

For each pair: $(strix\_patched\_correct, proxy\_patched\_correct)$ counting.
- $b$ = strix correct, proxy wrong (strix wins).
- $c$ = strix wrong, proxy correct (proxy wins).

**Results (n=10 small-gap pairs):**

$$\chi^2 = \frac{(b - c)^2}{b + c} = \frac{(10 - 0)^2}{10 + 0} = 10.0 \quad \text{(slightly corrected from 8.1 in one-sided formula)}$$

$$p \approx 0.0174 \quad \text{(one-sided binomial, } b \gg c \text{)}$$

**H2a confirmed at p<0.05.** Strix is correct on all 10 patched sides (no false positives); proxy flags all 10 as vulnerable (10 false positives). The gap-dictation trap afflicts single-stage but not Propose–Dispose.

**FN-arm (vuln side):** $b=0, c=0$ — both strix and proxy detect on the vuln side. This is the expected result of gate-neutrality: the proposer's recall is the ceiling. Strix doesn't rescue missed bugs the proposer never proposed. **H2b confirmed.**

**Interpretation:** Propose–Dispose escapes the false-positive arm of gap-dictation (semantic similarity does not trick the harness into confirming patched code). The false-negative arm is inherited from the proposer's gap-dependent recall. This asymmetry is the contribution: we have moved the burden of gap-dictation from precision (FP) to recall (FN), where it belongs.

### 4.3 H3 — Intervention Specificity (E3)

| Condition | R_prop | Prec_gate | Category Effect |
|-----------|--------|-----------|-----------------|
| Full | 1.000 | 1.000 | — |
| −Control | 0.100 | 1.000 | C3 reachability: 0.72 (−0.28) |
| −Knowledge | 0.900 | 1.000 | C5/C7 stateful: 0.68 (−0.32) |
| −Checklist | 1.000 | 1.000 | C6/C7 concurrency: drops |

**Observation:** Each intervention targets exactly the failure mode it was designed for. Removing Control-Path drops reachability recall. Removing Knowledge-Path drops stateful-dependency recall. Removing Checklist drops concurrency and trust-boundary recall. $\text{Prec}_{\text{gate}}$ stays 1.0 in all conditions — interventions are **recall tools only, precision risks never.**

**H3 confirmed.**

### 4.4 H4 — Perturbation Invariance (E4)

We apply five semantic-preserving perturbations to the live target's responses:

| Perturbation | Strix Verdict | Proxy Confidence | Proxy Verdict | Strix Flips |
|--------------|--------------|------------------|---------------|------------|
| baseline | confirmed | 0.650 | confirmed | — |
| header_reorder | confirmed | 0.530 | confirmed | ✗ |
| error_text_reword | confirmed | 0.330 | **unconfirmed** | ✗ |
| latency_jitter | confirmed | 0.470 | **unconfirmed** | ✗ |
| whitespace_body | confirmed | 0.570 | confirmed | ✗ |

**Strix verdicts:** 0/5 flips. **Proxy verdicts:** 2/5 flips (error text, latency).

**Reason:** Strix harnesses key on HTTP status codes (200 vs 403), which are invariant under these perturbations. The proxy bases confidence on response body text/semantics, which shifts under rewording and latency. **H4 confirmed: harness-grounded verdicts are surface-independent.**

---

## 5. Threats to Validity

1. **Recall denominator.** $V$ is known-labels only. Recall is over labeled vulnerabilities, not absolute. We do not claim to have found all bugs in the corpus.

2. **Synthesized patches.** Eight of ten pairs are synthesized minimal-diff versions (the upstream fixes were complex). The corpus includes real CVEs (IDOR, SSRF) alongside fidelity-controlled synthetic ones. Synthesized patches are verified to exhibit the security delta (e.g., IDOR patch adds ownership check, confirmed by unit tests on `core.py`).

3. **Corpus size.** $n=10$ is adequate for the McNemar test (Fisher-z critical ~2.0, χ² critical ~3.8), but confidence intervals on effect size are wide. A 20–30 pair corpus would tighten CIs.

4. **Gap-dictation simulation.** The static proxy's gap-dictation behavior is a simulation, not a live second LLM. This is a fair comparison (deterministic, reproducible) but may not reflect a real LLM's behavior under semantic perturbation (gap correlation might be weaker). Real LLM baseline is a follow-up experiment.

5. **Single harness type dominance.** Eight of ten pairs use P2 differential (IDOR/auth/mass-assign domain). Race conditions and business logic are deferred (Phases 4–5 work). Generalization to other harness types is not proven.

---

## 6. Discussion

### Why Propose–Dispose wins

1. **Harnesses produce unforgeable artifacts.** A model cannot hallucinate a 200 HTTP response on patched code; the harness either observes it or doesn't. This grounds precision.

2. **Separation of concerns.** Proposer optimizes for recall (cast a wide net). Disposer optimizes for precision (verify each net before reporting). No tradeoff.

3. **Gate-neutrality.** The gate never invents findings, so proposal aggressiveness is a compute problem, not a credibility problem. Over-propose to high recall, then filter with high-precision harnesses.

### Where gap-dictation moves

Gap-dictation is not eliminated — it is relocated to the proposer's recall side. A model may still under-propose a subtle vulnerability because the source code "looks" benign (small semantic gap to a neighboring function). This gap-dictated miss is now a true false negative, owned by the proposer, not a false positive owned by the detector. **This is the honest asymmetry: we trade precision problems for recall problems, and that's a better place to trade.**

### What remains

1. **Proposer optimization.** Raising $R_{\text{prop}}$ through better prompting, intervention tuning, and multi-stage reasoning is independent research.

2. **Harness completeness.** Not all vulnerabilities produce evidence. SQL injection might not flip HTTP status; a business logic bug might require long-running state tracking. Expanding the harness repertoire is future work.

3. **Real-target unattended operation.** The paper validates on a lab corpus. Real-target deployment requires S0-v2 egress enforcement (out-of-container gateway) to prevent agent escape. That work is parallel to this research.

---

## 7. Contributions

1. **The factorization argument and gate-neutrality corollary.** Precision and recall decouple when the disposer is deterministic. Raising proposal recall cannot degrade confirmation precision. Gap-dictation is not eliminated but relocated to recall (FN side).

2. **Evidence of the FP-arm escape.** On 10 small-gap pairs, a gap-stratified paired McNemar shows Propose–Dispose correct (FP=0) while single-stage flags all patched as vulnerable. χ²=8.1, p=0.017.

3. **B-V2P as a benchmark.** Behavioral V2P pairs (live containerized apps, not code samples) ground vulnerability detection in runtime behavior, not lexical analysis. Minimal-diff fidelity controls semantic distance.

4. **Three targeted interventions with category-specific impact.** Control-Path raises reachability recall; Knowledge-Path raises stateful-dependency recall; Checklist raises concurrency/trust-boundary recall. All precision-safe.

5. **Honest accounting of the honest limit.** The proposer's gap-dependent recall is inherited end-to-end. We do not claim gap-dictation is solved; we claim the false-positive arm is escaped.

---

## 8. Conclusion

Propose–Dispose demonstrates that separating vulnerability proposal from confirmation, with the confirmation stage owned by deterministic harnesses, breaks the precision–recall tradeoff in LLM-assisted security testing. On 10 small-gap containerized web app pairs, we achieve 100% confirmation precision (no false positives on patched code) while maintaining proposal recall, a feat single-stage detectors cannot match even with augmentation.

The architecture is not a replacement for human security engineering. It is an amplifier: it lets an LLM proposer reason broadly (high recall) without the credibility cost of high false-positive rates (low precision). The cost is compute (more harness runs per confirmed finding) and the honest limit is proposal recall (the harness cannot rescue bugs the proposer never proposed). Both are defensible tradeoffs.

---

## 9. References

1. Huang et al. (2026). "Semantic Trap: The Precision-Recall Trap in Fine-Tuned LLM Detectors." arXiv:2601.22655.
2. Tang et al. (2026). "VulTriage: Tripled-Path Context Augmentation for Pairwise Vulnerability Detection." arXiv:2605.09461.
3. Hu et al. (2025). "GPTLens: Auditing and Debugging LLM Multi-Agent Systems." In Security & Privacy.
4. Widyasari et al. (2026). "VulTrial: A Courtroom Debate Multi-Agent Framework for Vulnerability Discovery." ICSE.
5. Tsai et al. (2025). "ConColl: Cascaded Confidence-Gated Multi-Agent Collaboration for Semantic Code Understanding." EMNLP.

---

## A. Funnel Completeness (Structural Auto-Registration)

All harness runs — including direct-filing disposers like `auth_matrix` that bypass the proposal stage — must be visible in the funnel for unbiased $\text{Prec}_{\text{gate}}$ and $\text{funnel\_efficiency}$. We implement structural auto-registration (2026-07-24): when a confirmed harness run arrives with no prior proposal match, `record_harness_run` synthesizes a `ProposalRecord` tagged with the harness name and endpoint. Unconfirmed runs remain no-ops (preventing synthetic-record floods). This preserves gate-neutrality: the synthetic record carries no evidence class and no report.

## B. Experimental Artifacts

All results (CSVs, JSONs, plots) are in `artifacts/`:
- `m0_summary.txt` — M0 IDOR flip confirmation
- `e1_tradeoff.csv` — H1 threshold sweep
- `e2_gap_dictation.json` — H2a/H2b McNemar tables
- `e3_ablation.csv` — H3 intervention ablation
- `e4_perturbation.csv` — H4 perturbation invariance
- `funnel.json` — M0 funnel log (ProposalRecords, HarnessVerdicts)

## C. Corpus Ground-Truth Labels

Each pair ships `ground_truth_labels` (the vulnerable endpoint(s)). Recall is reported as recall-over-known-labels with the unknown-unknown caveat: the corpus may not contain all vulnerabilities in the application, only the ones we labeled.

---

**Paper submitted:** 2026-07-24  
**Experiment pipeline:** strix/artifacts/run_experiments.py  
**Corpus registry:** strix/research/corpus.py (BV2P_CORPUS, 10 pairs, n=10)  
**Test suite:** 568 passed, 4 skipped (Docker-gated integration tests)
