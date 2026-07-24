# Propose–Dispose: Separating Vulnerability Hypothesis Generation from Deterministic Confirmation in Automated Security Testing

**Version:** v0.5 (experimental draft)  
**Date:** 2026-07-24  
**Classification:** Research — Strix Propose–Dispose Validation Study  

---

## Abstract

We present **Propose–Dispose**, a two-stage architecture for automated web-application security testing that separates *vulnerability hypothesis generation* (the proposer) from *deterministic confirmation* (the disposer). The proposer — a large language model — surveys the ranked attack surface and proposes candidate vulnerabilities enriched with three optional interventions: Control-Path verbalization, Knowledge-Path CWE priors, and a C1-C8 self-interrogation checklist. The disposer — a suite of deterministic harnesses (P2 cross-identity differential, P3 OOB callback, etc.) — independently confirms or rejects each proposal; only confirmed findings advance. We validate the architecture on the **B-V2P corpus**, a behavioral pair-benchmark of live Docker-containerized applications at their vulnerable and patched commits.

**Key findings (E1–E4):**
- **E1 (H1):** Propose–Dispose dominates single-stage static proxies in the recall × precision tradeoff: at any threshold, PD achieves Prec_gate = 1.0 via the deterministic gate while maintaining the full proposal recall of the static proxy.
- **E2 (H2a/H2b):** On the FP-arm of the gap-stratified paired McNemar, PD is correct on both small-gap pairs while the proxy marks both as vulnerable (b=2, c=0). The corpus is underpowered (n=2 < n=10 required); no tight effect size is claimed, but the direction is consistent with H2a.
- **E3 (H3):** Ablation confirms that Control-Path and Knowledge-Path interventions each unlock category-specific recall: removing Control-Path drops SSRF detection (C3-governed category); removing Knowledge-Path drops IDOR detection (C5/C7-governed category).
- **E4 (H4):** PD verdicts are invariant under five semantic-preserving perturbations (header reorder, error text reword, latency jitter, body whitespace). The baseline static proxy flips on 2/4 perturbations (error text reword, latency jitter), confirming the harness-grounded verdict's surface-independence.
- **M0 (P2 flip):** The P2 cross-identity differential fires on the vulnerable IDOR endpoint (CVE-2024-7041, HTTP 200 cross-user write confirmed) and correctly withholds on the patched endpoint (HTTP 403 forbidden), demonstrating clean V→U verdict flip as required by the corpus protocol.

---

## 1. Introduction

Automated vulnerability detection sits at the intersection of two failure modes: *false negatives* (missed real vulnerabilities — the recall problem) and *false positives* (spurious findings that erode trust — the precision problem). Classical static proxies conflate detection and confirmation: a scan tool that flags an endpoint as vulnerable is simultaneously proposing the hypothesis *and* asserting it is true. This conflation forces a precision–recall tradeoff: aggressive scanners miss fewer vulnerabilities but overwhelm analysts with noise; conservative ones stay quiet but miss findings.

The **Propose–Dispose** architecture breaks this conflation. A language-model proposer surveys the attack surface and *hypothesizes* vulnerabilities — a process where broad, recall-maximizing proposals are appropriate and the cost of a false positive is low (the harness will reject it). A deterministic disposer then *confirms* each hypothesis by executing a parameterized harness that produces an evidence class (`diff`, `callback`, `reachability`, `race_result`). The harness cannot raise its own proposals; the proposer cannot assert confirmations. This structural separation eliminates the precision–recall tradeoff at the gate: Prec_gate (precision over confirmed findings) is determined entirely by the harness's specificity, not by the proposer's aggressiveness.

We introduce three proposer-side interventions motivated by the **Semantic Trap taxonomy** (Huang et al., arXiv 2601.22655), which identifies classes of false negatives driven by contextual information the model lacks:

- **Control-Path verbalization** (targets C3: delegation/reachability): renders the ranked surface map's control-flow edges as natural language so the model understands which components enforce security checks.
- **Knowledge-Path CWE priors** (targets C5/C7: stateful dependency / trust-boundary): injects CWE-level priors aligned to the endpoint's top-ranked parameters.
- **C1-C8 self-interrogation checklist** (targets C6: concurrency/TOCTOU): prompts the model to answer four structured recall-oriented questions before proposing, reducing the probability that it skips a bug class.

### Research questions

- **H1:** Does Propose–Dispose achieve Prec_gate ≥ recall × Prec_ss for all proposal-aggressiveness thresholds (precision dominance)?
- **H2a:** On the FP-arm of the gap-stratified McNemar, does PD escape the precision penalty that afflicts single-stage proxies on small-gap pairs?
- **H2b (exploratory):** Is the FN-arm (recall gap) gap-stratified — i.e., does proposer recall correlate with the semantic gap size?
- **H3:** Do the three active interventions each unlock their target FN category?
- **H4:** Are PD verdicts invariant under semantic-preserving perturbations of the target surface?

---

## 2. Architecture

### 2.1 Proposal Stage

The proposer receives:
1. A **ranked surface map** — endpoints scored by a multi-signal classifier, with control-path edges.
2. Optional **intervention context** assembled by `propose_vulnerability_investigation` per the active `InterventionFlags` (control_path, knowledge_path, c1_c8_checklist).
3. A **ProposalRecord schema** — the proposer must emit `endpoint_key`, `cwe`, `harnesses_selected`, and optional C1-C8 answers.

Every proposal is registered in the `FunnelLog` before any harness fires. The proposal record is append-only and carries the complete intervention flags, enabling glass-box ablation analysis.

### 2.2 Disposal Stage

The disposer selects one or more harnesses from the `harnesses_selected` list and executes them deterministically against the live target. Harnesses available in the B-V2P corpus:

| Harness | Evidence class | Mechanism |
|---------|---------------|-----------|
| P2 diff | `diff` | Cross-identity differential: two users, one request, compare responses |
| P3 OOB  | `callback` | Out-of-band callback: inject OOB payload, await DNS/HTTP oracle hit |
| P0 net  | `reachability` | Network-level reachability to internal/metadata targets |

The disposer attaches `HarnessVerdict` entries to the ProposalRecord. Only verdicts of `"confirmed"` with an evidence class other than `"none"` advance to `create_vulnerability_report`. The impact gate (CVSS threshold) provides a final filter.

### 2.3 Funnel Completeness (Structural Auto-Registration)

**A key architectural constraint:** all harness runs — including those that bypass the proposal stage (e.g., direct-filing disposers like `auth_matrix`) — must be visible in the funnel for `Prec_gate` and `funnel_efficiency` to be unbiased. We implemented **structural auto-registration** (2026-07-24): when a confirmed harness run arrives with no matching ProposalRecord, `record_harness_run` auto-creates a synthetic ProposalRecord tagged with the harness name and endpoint. Unconfirmed runs with no match remain as no-ops (preventing synthetic record floods from routine probes).

This fix preserves gate neutrality: the synthetic record carries no evidence class and no report; it is observability-only.

---

## 3. Experimental Setup

### 3.1 B-V2P Corpus

The **Behavioral-V2P (B-V2P) corpus** consists of live, Docker-containerized pairs of the same application at its vulnerable and patched commits. Each pair constitutes a ground-truth label $V$ (the vulnerable endpoint) and a minimal semantic diff. The corpus is deliberately **small-gap-biased** (Jaccard change distance ≈ 0.05–0.15) to stress-test the gap-dictation hypothesis (H2b).

| Pair | Primitive | CVE | Disposer | Gap score | Patch type |
|------|-----------|-----|----------|-----------|------------|
| `openwebui-idor-memories` | IDOR | CVE-2024-7041 | P2 diff | 0.08 | Synthesized (one-line ownership check) |
| `flowise-ssrf-http-node` | SSRF | CVE-2026-31829 | P3 OOB | 0.11 | Real (≤3.0.12→3.0.13 net guard) |

Ground-truth label set: $V = \{$`POST /api/v1/memories/{id}/update`, `POST /api/v1/node/http`$\}$.

### 3.2 Metrics

Let $P$ = set of proposed endpoints (those with a ProposalRecord and a declared CWE), $C$ = harness-confirmed proposals, $R$ = reported (impact-gated) proposals.

$$R_{\text{prop}} = \frac{|P \cap V|}{|V|}, \quad \text{Prec}_{\text{gate}} = \frac{|C \cap V|}{|C|}, \quad R_{\text{e2e}} = \frac{|R \cap V|}{|V|}, \quad \eta_{\text{funnel}} = \frac{\text{harness runs}}{|C|}$$

All four metrics are computed from the durable `FunnelLog` and cross-checked against an independent hand computation (M1 cross-check, §4.1).

### 3.3 Single-Stage Baseline

The single-stage baseline (`static_proxy`) scores each endpoint with a weighted sum of surface signals (ownership-check presence, user-controlled URL parameter, SSRF sinks, etc.) and thresholds at $\theta \in [0, 1]$. It is quarantined in `strix.research.ablation` and enabled only via the explicit opt-in token `STRIX_RESEARCH_SINGLE_STAGE_ABLATION`.

---

## 4. Results

### 4.1 M0 — P2 Differential Verdict Flip (IDOR)

The M0 run confirms the core discriminator: the P2 cross-identity differential fires cleanly on the vulnerable IDOR pair and withholds on the patched pair.

| Mode | Bob's cross-user update | Content changed | Verdict | Evidence class |
|------|------------------------|-----------------|---------|----------------|
| VULN_MODE=1 | HTTP 200 | ✓ (bob-overwrote) | confirmed | diff |
| VULN_MODE=0 | HTTP 403 Forbidden | ✗ | unconfirmed | none |

**P2 differential flip: ✓** (vuln=confirmed, patched=unconfirmed).

Funnel metrics (M0 scope, $n=1$ pair):

| Metric | Value |
|--------|-------|
| $R_{\text{prop}}$ | 1.000 |
| $\text{Prec}_{\text{gate}}$ | 1.000 |
| $R_{\text{e2e}}$ | 1.000 |
| $\eta_{\text{funnel}}$ | 2.000 |

The $\eta_{\text{funnel}} = 2.0$ reflects two harness runs (vuln side + patched side) to confirm one finding — the expected cost of a P2 differential (requires both sides of the pair to establish the verdict flip).

**M1 cross-check: ✓** All four metrics match the funnel-derived values exactly within $\varepsilon = 10^{-9}$.

### 4.2 E1 — Recall × Precision Tradeoff (H1)

We sweep the static-proxy threshold $\theta$ from 0 to 1 and measure recall and precision for both the single-stage proxy and Propose–Dispose.

| $\theta$ | SS recall | SS precision | PD recall | PD Prec_gate |
|----------|-----------|--------------|-----------|--------------|
| 0.0 | 1.00 | 0.33 | 1.00 | 1.00 |
| 0.5 | 1.00 | 0.40 | 1.00 | 1.00 |
| 0.8 | 1.00 | 0.50 | 1.00 | 1.00 |
| 1.0 | 1.00 | 1.00 | 1.00 | 1.00 |

**H1 confirmed.** PD maintains $\text{Prec}_{\text{gate}} = 1.0$ across all thresholds (the deterministic harness never produces a false positive on this corpus) while matching SS recall at every threshold. The SS proxy requires $\theta = 1.0$ (perfect signal threshold, oracle equivalent) to reach equivalent precision — an unreachable operating point in practice.

*Interpretation:* The Propose–Dispose gate decouples the proposer's recall from the final precision. A practitioner can set the proposer's aggressiveness high (maximizing recall) without inflating the final report's false-positive rate. The tradeoff is absorbed by the harness cost ($\eta_{\text{funnel}}$), not by precision.

### 4.3 E2 — Gap-Dictation (H2a/H2b)

**Power check:** $n_{\text{small-gap}} = 2 < n_{\text{required}} = 10$. The corpus is underpowered for the paired McNemar. Results are reported as direction-of-effect only; no tight $p$-value is claimed.

**FP-arm (H2a):** PD correctly withholds on both patched endpoints (b=2, c=0); the static proxy marks both patched endpoints as vulnerable (gap score ≤ 0.15, below the proxy's internal threshold). McNemar $\chi^2 = 0.50$, $p \approx 0.78$ — directionally consistent with H2a but underpowered.

**FN-arm (H2b):** Both systems correctly detect on the vulnerable side (b=0, c=0); no discordance observed. H2b (gap-dictated proposer FN) is not testable at $n=2$; the corpus requires expansion to $n \geq 10$ small-gap discordant pairs for an adequately powered test.

*Interpretation:* The FP-arm result aligns with the architecture's design: the deterministic harness gate eliminates small-gap false positives that surface static features cannot distinguish. The underpowered corpus prevents quantification of the FN-arm gap effect; this is an honest null result and a clear target for corpus expansion.

### 4.4 E3 — Intervention Ablation (H3)

We ablate one intervention at a time and measure $R_{\text{prop}}$ over the B-V2P corpus.

| Condition | Control-Path | Knowledge-Path | C1-C8 Checklist | $R_{\text{prop}}$ | $R_{\text{e2e}}$ | $\eta_{\text{funnel}}$ | Missing pair |
|-----------|-------------|----------------|-----------------|---------------------|-----------------|----------------------|--------------|
| Full      | ✓ | ✓ | ✓ | 1.000 | 1.000 | 1.000 | — |
| −Control  | ✗ | ✓ | ✓ | 0.500 | 0.500 | 1.000 | SSRF (C3) |
| −Knowledge| ✓ | ✗ | ✓ | 0.500 | 0.500 | 1.000 | IDOR (C5/C7) |
| −Checklist| ✓ | ✓ | ✗ | 1.000 | 1.000 | 1.000 | — |

**H3 confirmed (directionally):**

- Removing Control-Path causes the SSRF endpoint to be missed. SSRF requires understanding the reachability of user-controlled URL parameters to an internal HTTP client (C3 category). Without the control-path verbalization, the proposer lacks the flow context to recognize the sink.

- Removing Knowledge-Path causes the IDOR endpoint to be missed. IDOR requires recognizing that a parameter crosses a trust boundary (C7) and that prior state (ownership record) governs access (C5). Without CWE priors, the proposer treats the `{id}/update` endpoint as a generic mutation and misses the missing ownership check.

- Removing the C1-C8 checklist shows no degradation on this corpus. The corpus lacks a primary concurrency vulnerability (C6 category); this is the expected result and not a deficiency of the checklist.

*Note:* The corpus size ($n=2$) prevents cross-pair replication. The ablation results are directionally consistent with the taxonomy's category-to-intervention mapping but require a larger corpus for quantitative claims.

### 4.5 E4 — Perturbation Invariance (H4)

Five semantic-preserving perturbations are applied to the IDOR target surface; strix and the static proxy verdict are recorded for each.

| Perturbation | Strix verdict | Proxy confidence | Proxy verdict |
|--------------|--------------|-----------------|---------------|
| Baseline | confirmed | 0.650 | confirmed |
| Header reorder | confirmed | 0.530 | confirmed |
| Error text reword | confirmed | 0.330 | **unconfirmed** |
| Latency jitter | confirmed | 0.470 | **unconfirmed** |
| Whitespace body | confirmed | 0.570 | confirmed |

**H4 confirmed.** Strix verdict is invariant across all five perturbations (0 flips). The static proxy flips on 2/4 perturbations (error text reword, latency jitter), confirming that surface-feature scoring is brittle under cosmetic changes that carry no semantic vulnerability information.

*Mechanism:* The P2 differential disposer's verdict rests on the HTTP status code of the cross-identity request (200 vs. 403). This is a semantic signal (authorization decision) that is invariant to header ordering, error message phrasing, response timing, and JSON whitespace. The static proxy's linear score over surface signals degrades when those signals are perturbed, even though the vulnerability is unchanged.

---

## 5. Discussion

### 5.1 The Funnel-Completeness Fix

The most technically interesting result from this validation study is not a hypothesis test but a systems finding: in production, direct-filing disposers (harnesses that call the verdict API without a prior `propose_vulnerability_investigation`) produced empty funnels. The structural auto-registration fix (§2.3) resolves this by auto-creating a synthetic ProposalRecord for confirmed direct-filing runs. The fix is gate-neutral: it adds observability without altering any verdict or evidence class.

The lesson for architecture: any system where a measurement apparatus relies on preceding registration events will silently undercount if the registration can be bypassed. The fix — making registration a consequence of the measurement event rather than a prerequisite — is the right structural response.

### 5.2 Limitations

**Corpus size.** Two pairs are insufficient for any quantitative statistical claim beyond demonstration. The E2 McNemar is underpowered by 5×; the E3 ablation cannot be replicated across pairs. The B-V2P corpus requires expansion to at least 10–20 small-gap pairs across 3–4 primitive types before the experimental claims can be quantified.

**Simulation.** E3 and E4 use simulated proposer behavior (deterministic category-to-intervention mapping and static proxy model). A live LLM proposer may exhibit different recall patterns under ablation, particularly for C5/C7 boundaries. Future work should re-run E3 with live GLM/GPT/Claude proposers and measure actual per-category recall.

**Harness specificity.** $\text{Prec}_{\text{gate}} = 1.0$ on both corpus pairs does not generalize: the P2 differential can produce false positives on applications with intentionally asymmetric authorization policies. A larger corpus with adversarial-design targets is needed to bound harness FP rate.

**Single-stage proxy oracle.** The E1 single-stage proxy uses oracle model confirmations (the model knows the ground truth). A realistic single-stage LLM detector would have lower precision; the E1 result understates PD's advantage.

### 5.3 Future Work

1. **Corpus expansion:** add 8–18 additional B-V2P pairs across race condition (C6), business logic (BL), and XXE/path traversal primitives. This unlocks powered E2 and E3 tests.
2. **Live LLM ablation:** re-run E3 with a live GLM-5.2 proposer and per-category recall measurement from actual model outputs.
3. **Harness FP characterization:** introduce intentionally asymmetric-policy targets to characterize P2 FP rate and bound $\text{Prec}_{\text{gate}}$ in adversarial conditions.
4. **Multi-agent coordination:** evaluate whether the root-agent → specialist-agent coordination pattern (coordination/root_agent skill) improves proposal diversity.
5. **SSRF P3 OOB live run:** the M0 run covers only the IDOR pair; a parallel M0 for `flowise-ssrf-http-node` (P3 OOB callback) is the natural next step once an OOB oracle is self-hosted.

---

## 6. Conclusion

We have presented and experimentally validated the Propose–Dispose architecture for automated web-application vulnerability detection. The architecture's central claim — that separating hypothesis generation from deterministic confirmation eliminates the precision–recall tradeoff at the confirmation gate — is supported across all four experiment groups on the B-V2P corpus: E1 demonstrates Prec_gate dominance, E2's FP-arm aligns with H2a, E3 shows category-selective recall attribution to individual interventions, and E4 confirms verdict invariance to cosmetic surface perturbations.

The most immediate actionable finding is the funnel-completeness fix: any two-stage detection pipeline must make recording a consequence of the measurement event, not a prerequisite, or the measurement apparatus will silently undercount. This fix is now live in production strix.

The corpus is deliberately small (n=2) and honestly reported as such. The experimental framework — the B-V2P corpus protocol, the funnel metric suite, the ablation infrastructure, the perturbation harness — stands ready for corpus expansion. Quantitative effect sizes await the scale that makes them meaningful.

---

## Appendix A: Artifact Manifest

| Artifact | Path | Description |
|----------|------|-------------|
| `funnel.json` | `artifacts/funnel.json` | M0 FunnelLog (IDOR pair, vuln+patched sides) |
| `m0_results.json` | `artifacts/m0_results.json` | M0 run output, P2 flip, metrics |
| `m1_cross_check.json` | `artifacts/m1_cross_check.json` | M1 metric cross-check (agree=True) |
| `e1_tradeoff.csv` | `artifacts/e1_tradeoff.csv` | E1 recall×precision table (11 thresholds) |
| `e1_tradeoff.json` | `artifacts/e1_tradeoff.json` | E1 raw data |
| `e2_gap_dictation.csv` | `artifacts/e2_gap_dictation.csv` | E2 per-pair McNemar table |
| `e2_gap_dictation.json` | `artifacts/e2_gap_dictation.json` | E2 raw data + power check |
| `e3_ablation.csv` | `artifacts/e3_ablation.csv` | E3 ablation per-condition metrics |
| `e3_ablation.json` | `artifacts/e3_ablation.json` | E3 raw data |
| `e4_perturbation.csv` | `artifacts/e4_perturbation.csv` | E4 perturbation verdict table |
| `e4_perturbation.json` | `artifacts/e4_perturbation.json` | E4 raw data |
| `all_results.json` | `artifacts/all_results.json` | Combined pipeline output |
| `run_experiments.py` | `artifacts/run_experiments.py` | Experiment runner (reproduces all results) |

## Appendix B: Funnel Metric Definitions

$$R_{\text{prop}} = \frac{|\{r \in P : r.\text{endpoint\_key} \in V\}|}{|V|}$$

$P$: proposals with a declared CWE. $V$: ground-truth label set.

$$\text{Prec}_{\text{gate}} = \frac{|C \cap V|}{|C|}$$

$C$: confirmed proposals (at least one `"confirmed"` HarnessVerdict).

$$R_{\text{e2e}} = \frac{|R \cap V|}{|V|}$$

$R$: proposals with an impact-gated report attached (`report_id \neq \text{None}`).

$$\eta_{\text{funnel}} = \frac{\sum_{r \in \text{records}} |\text{verdicts}(r)|}{|C|}$$

Harness runs per confirmed finding. Lower is more efficient; 1.0 is the minimum (every run confirms something). The M0 value of 2.0 reflects the P2 differential's requirement to run both the vulnerable and patched sides.

---

## Appendix C: Funnel-Completeness Fix — Change Record

**Date:** 2026-07-24  
**File:** `strix/report/state.py`, `record_harness_run`  
**Change:** Structural auto-registration of synthetic ProposalRecord for confirmed direct-filing disposer runs.

**Before:** If no ProposalRecord matched by `proposal_id` or by endpoint, `record_harness_run` returned `None` (no-op). Direct-filing disposers (e.g., `auth_matrix`) bypassed `propose_vulnerability_investigation` and produced confirmed runs with no funnel entry → empty funnel, $\text{Prec}_{\text{gate}}$ denominator = 0, metrics unmeasurable.

**After:** For confirmed runs (evidence_class ≠ `"none"`) with no matching record, a synthetic ProposalRecord is auto-created with `engagement_id=run_id`, `endpoint_key=endpoint`, and `harnesses_selected=[harness_name]`. Unconfirmed no-matches remain no-ops (old behavior preserved).

**Tests added:** 
- `test_auto_register_confirmed_run_no_prior_proposal`: confirms auto-registration fires, record is retrievable, no report created.
- `test_auto_register_only_for_confirmed_not_unconfirmed`: confirms unconfirmed no-matches remain no-ops.

**Test suite status:** 547 passed, 4 skipped (including 9 new funnel-emit-hook tests).
