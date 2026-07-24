# Propose–Dispose Paper — v1 (H1-first) Skeleton & Production Checklist

> Modest-scope **preprint v1**. Lead claim: **H1** (the propose–dispose architecture breaks the
> precision/recall trade — pushing proposal recall does *not* leak into confirmation precision).
> **H2** (the comparative gap-dictation study) is pre-registered and **deferred to v2**.
> Audience note: each section below has a one-line plain-language gloss of what it does in a paper.

---

## The one sentence v1 has to earn

> *"Because a deterministic harness — not the model — owns confirmation, you can make the LLM
> propose as aggressively as you like and the confirmed-finding precision (`Prec_gate`) stays
> essentially flat. Recall goes up; false positives don't follow it."*

That is H1. Everything in v1 exists to support exactly that, honestly and no further.

---

## Section map (standard CS/security paper structure)

**1. Abstract** *(the whole paper in ~200 words)*
- The problem (single-stage and LLM-critic detectors are stuck on a precision/recall trade), the
  idea (agent-proposes / harness-disposes), the result (H1: `Prec_gate` invariance), and the
  honest scope (architecture + H1 demonstrated; comparative study forthcoming).

**2. Introduction** *(why this matters, what we claim)*
- The trap: to catch more (recall↑), single-stage detectors loosen thresholds and false positives
  rise (precision↓). LLM-as-judge "critics" inherit the model's own blind spots.
- The thesis: decouple the two — **recall is the proposer's job, precision is the harness's job**
  — so they stop trading against each other.
- Contributions, stated plainly: (i) the architecture; (ii) its type-level enforcement (`C ⊆ P`,
  no `evidence_class` on a proposal); (iii) the instrumentation that makes the claim measurable;
  (iv) the H1 result.

**3. Background / Related Work** *(what's been done, what we build on)*
- The precision/recall trap and gap-dictation framing.
- LLM-as-judge artifacts and their failure modes (cite the C1–C8 taxonomy as an *artifact*, not
  ground truth — the spec already flags this).
- The McNemar paired-test template (the tool v2 will use) — introduced here, *used* in v2.

**4. System Design — Propose–Dispose** *(the core contribution)*
- Agent proposes candidates; deterministic harnesses dispose. Precision never owned by a model.
- The disposers: semantic differential (diff), native OOB oracle (callback), reachability,
  race harness (race_result), business-logic gate. The **impact gate**: every finding carries an
  `evidence_class`; `none` downgrades.
- **The enforcement is structural**, not convention: the proposal stage carries no `evidence_class`
  and no report state, so a proposal *cannot* express a disposition. `C ⊆ P`: the gate only
  removes proposals, never invents findings.
- *(If SGL has landed:)* one paragraph that the measurements describe the **hardened** engine.

**5. Instrumentation & Metrics** *(how we can measure the claim at all)*
- The funnel (`ProposalRecord` / `FunnelLog`) and the four derived metrics: `R_prop` (proposal
  recall), **`Prec_gate` (the load-bearing number)**, `R_e2e` (end-to-end recall),
  `funnel_efficiency`.
- **Recall-over-known**: every recall figure is over the labeled set only, with the
  unknown-unknown caveat stated explicitly.

**6. Methodology — B-V2P pairs + the single-stage baseline** *(the experimental setup)*
- **Behavioral-V2P**: the same app at a vulnerable commit and its minimal-diff patch, deployed
  live. The deterministic disposer's verdict must *flip* vuln→fixed while the raw model proposal
  does not — that flip is the unit of measurement.
- The **single-stage ablation** (M4, quarantined research-only): the comparison baseline where the
  model self-confirms — used here as the "what the trap looks like" contrast.
- The two seeds, presented as the walking skeleton: **IDOR (CVE-2024-7041)** via the real diff
  disposer; **SSRF (CVE-2026-31829)** via the real OOB/net classifier.

**7. Results — v1 = H1 only** *(the new evidence; this is what E1 produces)*
- **The headline figure:** `Prec_gate` (y) vs `R_prop` (x), swept across proposal aggressiveness,
  for both modes. Single-stage shows recall↑ / precision↓ (the trap). Propose–dispose shows
  `R_e2e`↑ with **`Prec_gate` ≈ flat**. Gate leakage (`Prec_gate` dropping as `R_prop` rises) is
  the thing that would *falsify* H1 — report it whether or not it appears.
- **The single-number demonstrations (M0):** for each of the two seeds, the harness flips
  vuln→confirmed / patch→unconfirmed while the raw proposal does not. A small table.
- *(Optional, clearly labeled DESCRIPTIVE — no significance claim):* the E2 2×2 on the two seeds,
  shown only to preview direction, explicitly underpowered.

**8. Limitations & Threats to Validity** *(the honesty section — reviewers read this closely)*
- The comparative claim (H2a, gap-stratified McNemar) is **pre-registered and forthcoming**;
  the current corpus is **underpowered** for it — say so plainly.
- Recall is recall-over-known; unknown-unknowns are out of reach.
- The C1–C8 taxonomy is an LLM-as-judge artifact, not ground truth.
- Small n; two primitives (IDOR/SSRF); race/business-logic pairs deferred.

**9. Conclusion + Forthcoming** *(what we showed, what's next)*
- H1 holds: precision is decoupled from recall in this architecture. v2 will report the
  pre-registered comparative study (H2a/H2b) on a powered corpus.

---

## What each experiment must actually produce for v1

| Deliverable | Produces | Status / owner |
|---|---|---|
| **E1 — tradeoff curve (H1)** | The headline `Prec_gate` vs `R_prop` figure, both modes, across an aggressiveness sweep. **This is the paper's load-bearing result.** | Live run, operator host |
| **M0 — single-number demos** | Per-seed flip table (harness flips vuln↔patch; raw proposal doesn't), IDOR + SSRF | Mechanism already tested; needs the live datapoint |
| **M1 — funnel metrics** | The four metrics computed off the funnel, cross-checked vs hand computation | Code done (`strix/research/metrics.py`) |
| **M4 — single-stage baseline** | The contrast curve (the trap) for E1 | Code done (quarantined) |
| **E2 (descriptive preview only)** | The 2×2 on two seeds, labeled underpowered — *optional* | From the same runs |
| **Deferred to v2** | E2 powered McNemar (H2a/H2b), E3 ablation (H3), E4 perturbation (H4), grown corpus | Not in v1 |

**Pre-registration note:** E1/H1 is descriptive-comparative and doesn't require the E2 lock. But
do **not** read or report E2 inferentially in v1 — keep any E2 content strictly descriptive, or
omit it — so the v2 pre-registered McNemar stays clean (no peeking).

---

## Why this is the right v1
- It's a **complete, honest, standalone contribution**: a novel architecture + the one result that
  makes it interesting, with the limitations stated. That's publishable as a preprint today.
- It **timestamps the architecture claim** (precedence) while the corpus for H2 grows.
- It **doesn't block bounty hunts** — those gate on the HOLD LINE, not the paper.
- v2 then *adds* H2 (a new arXiv version, or a full venue paper) without retracting anything in v1.

## Minimal path to v1 submittable
1. Land SGL-Core to the HOLD LINE (so v1 describes the hardened engine).
2. Run **E1** + the **M0** demos on the operator host.
3. Drop the results into sections 7–8 (the v0.4 draft already has 1–6 and 9 largely framed).
4. Internal traceability pass (every number → a funnel artifact) + one review round.
5. Post arXiv v1. Start bounty hunts in parallel. Grow corpus toward v2.
