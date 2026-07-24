# E2 Pre-Registration — Gap-Dictation (H2a / H2b)

> **Research-validity Gate 4 artifact.** This document fixes E2's gap metric, primary test, and
> equivalence margin **before any outcome is observed**. Lock it (fill the `[LOCK: …]` fields,
> set the status to LOCKED, record the commit) **before** the first E2 run. Anything decided after
> data is seen is exploratory and must be reported as such — never as a confirmatory E2 result.

- **Spec:** `propose-dispose-validation` (F-PD-B). Canonical narrative: `../paper/propose-dispose-research-proposal-v0.4.md`.
- **Status:** `DRAFT` → set to `LOCKED` on sign-off.
- **Locked by / date / commit:** `[LOCK: name]` / `[LOCK: YYYY-MM-DD]` / `[LOCK: git sha of the corpus + harness]`
- **No-peek commitment:** outcomes (verdicts, the discordant 2×2, any metric) are **not inspected** until this file is LOCKED and the corpus + run scripts are frozen at the recorded commit.

---

## 1. Hypotheses under test

- **H2a (the win):** the strix pipeline (proposer → deterministic disposer) is **pairwise more often correct** than a single-stage proxy on the B-V2P pairs — the false-positive-arm win.
  - **Mechanism fingerprint (secondary):** the strix advantage **widens as the surface gap shrinks** (small-gap pairs are where a single-stage detector is most gap-dictated).
- **H2b (the honest limit):** proposer recall is **gap-dependent** — on small-gap pairs the proposer may miss the vuln, an inherited false-negative the neutral gate does not rescue. *Win-either-way:* if recall is flat across the gap, frontier proposers don't inherit the trap at all (a stronger result).

The headline is bounded: **strix escapes the false-positive arm of gap-dictation; the false-negative arm is the proposer's recall problem.** No "escapes gap-dictation" claim.

---

## 2. Design & units

- **Unit:** one B-V2P pair (a vuln deployment + its minimal-diff patch), from `strix/research/corpus.py::BV2P_CORPUS`.
- **Per-pair decomposition (so H2a/H2b cannot confound):**
  - **FP-arm** = the **patched** side: a correct system returns *no* finding. A false positive = a confirmed finding on the patched deployment.
  - **FN-arm** = the **vuln** side: a correct system returns the finding. A false negative = no finding on the vuln deployment.
- **Systems compared:** (A) strix pipeline; (B) single-stage proxy = the M4 `strix.research.ablation` baseline (`self_confirm` and/or `static_proxy`), **build-time/entrypoint gated, off in production**. Dynamic range of (B) is matched to (A) to avoid the floor-effect confound.
- **Correctness of a system on a pair** = correct on **both** arms (no FP on patch ∧ no FN on vuln). This is the per-pair binary outcome entering McNemar.

---

## 3. Gap metric (registered definition)

The **surface gap** of a pair quantifies how much the vuln and patch deployments differ at the attack surface a single-stage detector can see (tokens/structure), independent of behaviour:

- **g(pair)** = normalized surface distance between the vuln and patch responses/spec for the pair's `vuln_endpoint`, computed as the **Jaccard distance over the bag of structural tokens** (status line, header names, body-structure keys after the P1 volatile-field normalizer) of the two deployments' responses to the identical probe set:
  `g = 1 − |T_vuln ∩ T_patch| / |T_vuln ∪ T_patch|`, with `g ∈ [0, 1]`.
- **Stratification:** `small-gap` iff `g ≤ τ`, else `large-gap`. **`[LOCK: τ = 0.15]`** (recommended default; set before runs).
- Rationale: the harness consumes *behaviour*, so it is gap-invariant by construction; the test targets the *pipeline vs a single-stage proxy*, and the mechanism fingerprint is that (A)−(B) widens as `g → 0`.
- The gap metric is computed from the **frozen** probe set + normalizer at the locked commit; it is **not** re-tuned after seeing outcomes.

---

## 4. Primary analysis (confirmatory)

- **Test:** **gap-stratified paired McNemar, one-sided** (VulTriage Appendix C template).
- **2×2 (within the small-gap stratum):** discordant cells are
  - `b` = pairs where **strix correct, single-stage wrong**
  - `c` = pairs where **single-stage correct, strix wrong**
- **Statistic:** exact binomial McNemar on `(b, c)` (exact, not χ² — small n). **One-sided** alternative: `b > c` (strix wins the FP-arm).
- **α = `[LOCK: 0.05]`** (one-sided). **Primary stratum = small-gap.** The large-gap stratum is reported descriptively.
- **Primary decision (H2a):**
  - **Confirm H2a** iff the one-sided exact McNemar p < α **and** `b > c`.
  - **Refute** iff `c ≥ b` (no FP-arm advantage) at adequate discordant count.
  - **Inconclusive** iff the discordant count is below the power floor (§6) — reported as underpowered, **not** as refutation.

---

## 5. Equivalence margin δ (registered)

`δ` bounds what counts as a **negligible** difference, used for the non-superiority / "constant" claims so they are not framed as "proving the null":

- **δ = `[LOCK: 0.10]`** on the proportion scale (recommended default).
- **Uses:**
  1. **H1 tie-in (gate non-leakage):** `Prec_gate` is declared **"≈ constant" as `R_prop` rises** iff the change in `Prec_gate` across the aggressiveness sweep stays within **±δ** (a TOST-style equivalence reading), with **gate leakage (`Prec_gate` < 1 by more than δ) as the primary watch**. A material drop beyond δ falsifies H1.
  2. **H2b flat-recall (the stronger result):** proposer recall is declared **gap-independent** iff the small-gap vs large-gap recall difference is within **±δ**; a drop beyond δ on small-gap pairs is the inherited FN (H2b as stated).
- δ is fixed here; CIs are reported against it, never reverse-engineered from the observed effect.

---

## 6. Power & stopping

- The primary test needs **discordant small-gap pairs**, not breadth. Target discordant count **`[LOCK: n_discordant ≥ 10]`** before the one-sided exact McNemar is treated as adequately powered for α and a minimum detectable `b/(b+c)` of **`[LOCK: 0.8]`**.
- `strix.research.corpus.power_check(required_discordant=n_discordant)` gates this: with the current seed corpus it returns `sufficient = False` — **so E2 is not yet runnable to a confirmatory conclusion**; grow the small-gap corpus first. **No tight effect size (ρ, odds ratio) is reported from tiny n.**
- **Stopping rule:** the corpus + probe set are frozen at the locked commit; runs proceed until every pair is evaluated. No data-dependent stopping, no pair added/removed after unblinding.

---

## 7. Secondary / illustrative (explicitly non-confirmatory)

- Difference-of-correlations (gap vs correctness, per system) + **bootstrap CIs** — **illustrative only**; an underpowered interaction is reported as such, never as falsification of H2a.
- The margin-widens-as-gap-shrinks trend (H2a mechanism fingerprint) is **secondary**: reported with its CI, not used to confirm/refute the primary.

---

## 8. Traceability & integrity

- Every reported number resolves to a funnel artifact via `strix.research.metrics` (`summarize_funnel` + `traceability`); the four metrics are **cross-checked against the M0 hand computation** (`cross_check`) before any E2 claim (TG1.2 / TG5.7).
- Recall is reported as **recall-over-known** (`ground_truth_labels`) with the unknown-unknown caveat — never absolute recall.
- No magnitudes are imported from the cited papers; the single-stage baseline is **self-measured** (M4). The C1–C8 taxonomy is treated as an LLM-as-judge artifact.
- The M4 self-confirm baseline is the only forbidden-path component; it is confirmed **off in production** (PBT 4.4 / 4.6) for every run that produces an E2 number.

---

## 9. Frozen vs analyst-discretion

| Frozen at lock (this doc) | Analyst discretion (report transparently) |
|---|---|
| Hypotheses, arms, per-pair correctness rule | Plot styling, table layout |
| Gap metric, τ, stratification | Narrative framing within the bounded headline |
| Primary test, α, one-sided direction | Choice of bootstrap resamples (report the number) |
| δ and its two uses | — |
| Power floor, stopping rule, corpus commit | — |

---

### Lock line

> On lock, set **Status: LOCKED**, fill every `[LOCK: …]`, and record the frozen corpus+harness commit. After this line is committed, E2 outcomes may be unblinded and analyzed under the rules above.
>
> `Status: DRAFT — not yet locked.`
