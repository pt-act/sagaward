# Paper patch vP-0.1 → vP-0.2 — formal-decomposition correction + provenance reframe

**For:** proposal author (strix program)
**From:** PM / research-synthesis review
**Re:** `propose-dispose-paper.md` (living preprint vP-0.1)
**Scope:** two issues — (F1) the `R_e2e` decomposition formula is mathematically wrong in three places and collapses a second false-negative locus; (F2) the convergent-derivation claim should be a process claim, not a chronology claim. Thesis unaffected; F1 *strengthens* the recall argument. Exact replacement text below.

---

## F1 — Correct the decomposition (5 edits)

**The error.** `R_e2e = R_prop · Prec_gate` is false. From §3.1's own definitions, the algebra gives `R_e2e = R_prop · (|C∩V|/|P∩V|)`. The second factor is **gate sensitivity** (`S_gate` — of the real vulns proposed, how many the harness confirmed), **not** `Prec_gate` (precision — of confirmations, how many are real). Same numerator, different denominators; equal only if the harness makes zero false confirmations *and* zero true-proposal misses simultaneously. The fix also surfaces a second FN locus the paper currently attributes entirely to the proposer.

> Define once, then reuse: **`S_gate = |C∩V| / |P∩V|`** = gate sensitivity (the harness's confirmation recall on true proposals). `Prec_gate = |C∩V| / |C|` stays as defined (confirmation precision).

### Edit 1 — Abstract (replace the formula sentence)

**FROM:**
> We formalize this as `R_e2e = R_prop · Prec_gate` with the two factors owned by independent components, and we prove a corollary — the gate can only remove proposals, never add findings (`C ⊆ P`) — whose consequence is that gap-dictation is not eliminated but **relocated**…

**TO:**
> We formalize end-to-end recall as `R_e2e = R_prop · S_gate`, the product of proposal recall (owned by the proposer) and gate sensitivity (owned by the harness), and we show the decoupling claim separately: confirmation precision `Prec_gate` stays ≈ 1 *independent of* `R_prop`, because a different, non-generative component owns it. A definitional containment — the gate can only remove proposals, never add findings (`C ⊆ P`) — has the consequence that gap-dictation is not eliminated but **relocated**…

*(Also drops "prove a corollary": `C ⊆ P` is true by definition of `C`, not a proven result.)*

### Edit 2 — §1 Contribution 1 (replace the parenthetical)

**FROM:**
> 1. **The factorization argument** and its formal recall/precision decomposition (`R_e2e = R_prop · Prec_gate`), with the specific claim…

**TO:**
> 1. **The factorization argument** and its formal recall decomposition (`R_e2e = R_prop · S_gate`, with `Prec_gate` ≈ 1 held *independently* of `R_prop` — the precision-decoupling claim, not a factor of the identity), with the specific claim…

### Edit 3 — §3.1 (replace the closing two lines after the metric list, and add `S_gate` to the list)

Add to the bullet list (after `Prec_gate`):
> - **Gate sensitivity (confirmation recall)**: `S_gate = |C ∩ V| / |P ∩ V|` — of the true vulns the proposer *proposed*, the fraction the harness *confirmed*. (Distinct from `Prec_gate`: same numerator, denominator `|P∩V|` vs `|C|`.)

**FROM (the two lines after the list):**
> - **End-to-end recall**: `R_e2e = |C ∩ V| / |V| = R_prop · (|C ∩ V| / |P ∩ V|)`
>
> In a single-stage detector, raising recall lowers precision — the trap. In propose–dispose, `Prec_gate` is owned by the **harness**, not the proposer; raising `R_prop` cannot lower `Prec_gate` because a different component owns it.

**TO:**
> - **End-to-end recall**: `R_e2e = |C ∩ V| / |V| = R_prop · S_gate` — proposal recall times gate sensitivity.
>
> Two distinct claims follow, and the paper keeps them separate. **(i) Precision decoupling (the trap-break, H1):** in a single-stage detector raising recall lowers precision; in propose–dispose `Prec_gate` is owned by the **harness**, not the proposer, so raising `R_prop` cannot lower `Prec_gate` — a *different* component owns it. **(ii) The recall identity:** `R_e2e = R_prop · S_gate` shows end-to-end recall is the product of two recall terms — what the proposer surfaces (`R_prop`) and what the harness can actually fire on (`S_gate`) — neither of which is `Prec_gate`. Conflating `S_gate` with `Prec_gate` would overstate `R_e2e`; we report both `S_gate` and `Prec_gate` off the funnel.

### Edit 4 — §3.3 (append after the FP/FN-arm bullets, before "The honest headline…")

**ADD:**
> Note this places the false-negative arm in **two** loci, not one. `R_e2e = R_prop · S_gate` has two recall terms below 1: a **proposer miss** (`R_prop < 1` — the subtle vuln was never proposed, the gap-dictation case above) and a **gate miss** (`S_gate < 1` — the vuln *was* proposed but the harness could not produce its artifact, e.g. a genuinely vulnerable blind SSRF whose callback is egress-filtered, so the OOB oracle returns *unconfirmed*). The first is the proposer's recall ceiling; the second is the harness's sensitivity ceiling. Both are measured directly off the funnel; the headline below concerns the proposer locus, but `S_gate` is reported alongside it so the ceiling claim is exact.

### Edit 5 — §8 (replace the "ceiling is proposal recall" sentence)

**FROM:**
> This reframes the engineering frontier — the ceiling of an evidence-gated agent is its **proposal recall**, which is why the recall interventions (§5, H3) target the false-negative drivers…

**TO:**
> This reframes the engineering frontier — the recall ceiling of an evidence-gated agent is the product `R_prop · S_gate`: what the proposer surfaces *and* what the harness can fire on. Proposal recall (`R_prop`) is the dominant, model-driven term and the open problem the recall interventions (§5, H3) target the false-negative drivers of; gate sensitivity (`S_gate`) is the harness-side term, reported off the funnel so a recall loss is correctly attributed to proposer vs. gate rather than blamed wholesale on the proposer…

### Edit 6 — Appendix A Claims Ledger (replace one row, add one row)

**REPLACE row:**
> | `R_e2e = R_prop · Prec_gate`, factors owned by independent components | `architectural` |

**WITH:**
> | `R_e2e = R_prop · S_gate` (recall identity); `Prec_gate ≈ 1` held independently of `R_prop` (precision decoupling) | `architectural` |

**ADD row (under the `under-test` group):**
> | Gate sensitivity `S_gate < 1` is a second FN locus distinct from proposal recall | `architectural` premise; **magnitude** `under-test` (measured off funnel) |

---

## F2 — Reframe the convergent-derivation claim (2 edits)

**The issue.** The arXiv timestamps (SemanticTrap 2601.22655, VulTriage 2605.09461 — both May 2026) predate the strix specs (created 2026-06-14). The derivation *was* independent — the author found the papers later — but wording it as temporal priority invites a date-checking reviewer to call it overstated. Make it a process claim.

### Edit 7 — Abstract / §1 framing wherever "found after the strix specs were written" appears

**FROM (e.g. §6 source-of-truth note / Appendix B framing):** "…found *after* the strix specs were written…"

**TO:** "…**derived independently of** this prior work (the strix propose–dispose specs were conceived without reference to it; the convergence was identified afterward)…"

### Edit 8 — Appendix B.1 (replace the "written before" sentence)

**FROM:**
> 1. **Convergent validation.** The strix specs (the propose-dispose doctrine, impact-gating) were written *before* the Semantic Trap and VulTriage papers were found. Two independent derivations landing on "the model cannot self-confirm; gate on observed evidence" de-risks the premise.

**TO:**
> 1. **Convergent (independent) derivation.** The strix propose–dispose doctrine and impact-gating were reasoned out **without reference to** the Semantic Trap and VulTriage papers, which the author encountered only afterward. We make no claim of temporal priority — those papers' arXiv versions predate these specs — but the derivation was independent, and two independent routes landing on "the model cannot self-confirm; gate on observed evidence" de-risks the premise.

---

## What does NOT change
- The thesis, hypotheses (H1–H4), B-V2P design, McNemar protocol, the §6-empty discipline, and the Claims Ledger structure are all sound and untouched.
- F1 is a correctness fix that *strengthens* the paper: it yields the `S_gate` number and a precise two-ceiling recall story instead of an over-broad "proposal recall is the ceiling."
- Bump the version line to **vP-0.2** and add a one-line changelog: *"vP-0.2: corrected recall decomposition (R_e2e = R_prop · S_gate; Prec_gate is the separate precision-decoupling claim); added gate-sensitivity as a second FN locus; reframed convergent derivation as independent-not-prior."*
