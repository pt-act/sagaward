# `conceptual/` — Propose–Dispose working archive

> **This directory is a working archive and provenance trail, not the source of truth.**
> The narrative drafts here are **superseded** by the consolidated paper. Don't cite or edit them — go to the paper.

---

## Where to look now

| You want… | Go to |
|---|---|
| **The science / the thesis / hypotheses / method / results** | **`propose-dispose-paper.md`** — the consolidated *living preprint* (vP-0.1, **pre-empirical**). The single scientific source of truth. |
| **What to build (execution)** | `.agents/specs/propose-dispose-instrumentation/` (the funnel + assembler `unit`) and `.agents/specs/propose-dispose-validation/` (the B-V2P corpus, experiments, quarantined ablation mode). |
| **How it enters the program graph** | `manifest.yml` (the two spec entries + the non-gating `propose-dispose-validated` milestone). |

Everything in this folder feeds one of those three. Nothing here is canonical on its own.

---

## What's in here

This directory holds **two distinct kinds** of file. Keep them straight:

### A. Superseded narrative drafts — *provenance only, do not edit*

These were the iterative proposal and the cross-role dialectic that produced it. They are now **folded into the paper** and kept solely as history (the paper's Appendix B is the curated version of this trail).

| File | Role in the lineage | Folded into |
|---|---|---|
| `propose-dispose-research-proposal.md` | v0.1 — first proposal (thesis, B-V2P, M0–M5) | paper §§3–7 |
| `propose-dispose-research-proposalV0.2.md` | v0.2 — non-generative-disposer positioning + 4-rung ladder | paper §2, §9 |
| `propose-dispose-research-proposalV0.3.md` | v0.3 — M4 safety guardrail, C2-at-the-gate, C1/C2 symmetry | paper §3, §5 |
| `propose-dispose-research-proposal-v0.4.md` | v0.4 — stats reframe, **H2a/H2b split**, McNemar-primary, M0 seed re-rank | the consolidation basis of the paper |
| `propose-dispose-v0.3-to-v0.4-stats-patch.md` | PM stats patch (prove-the-null → difference-of-correlations) | paper §5 + Appendix B |
| `propose-dispose-note-to-PM-stats-escalation.md` | author escalation (aim correction → the FP-arm/FN-arm split) | paper §3.3 + Appendix B |
| `propose-dispose-PM-response-and-path-forward.md` | PM ruling: accept escalations, **split into two specs** | paper Appendix C + the spec triplets below |

### B. Staged execution specs — *NOT superseded; these go live*

The two spec triplets staged under `propose-dispose/specs/` are the **real execution specs**, destined for `.agents/specs/`. They are not history — they are the build plan.

| Path | Type | Notes |
|---|---|---|
| `propose-dispose/specs/propose-dispose-instrumentation/` | `unit` (product DAG) | funnel/`ProposalRecord` (M1) + proposal-context assembler (M3). Spec triplet complete. |
| `propose-dispose/specs/propose-dispose-validation/` | `research` (non-gating) | B-V2P corpus (M2), quarantined single-stage ablation (M4), experiments (M5). **See the canonical-version note below.** |
| `propose-dispose/propose-dispose-manifest-integration.md` | — | the draft `manifest.yml` entries (coder applies). |

> **Canonical validation `spec.md` / `tasks.md`.** The validation spec was reformatted into the standard Spec-Architect **PBT-variant** format (consistent with the phase specs and the instrumentation sibling). The canonical `spec.md` and `tasks.md` are those **reformatted** versions; the full research narrative that v0.4 carried now lives in **the paper** (it is the spec's research companion). The validation `planning/requirements.md` line *"spec.md = v0.4"* should be read as *"spec.md = canonical Spec-Architect format; research narrative = `propose-dispose-paper.md`."*

---

## Lineage (the dialectic, in one line)

`v0.1 → v0.2 → v0.3 → v0.4 → consolidated paper`, sharpened across roles (visionary · PM/architect · implementer · research synthesis). Five corrections each removed an over-claim — the stats reframe, the aim correction (harness can't be gap-dictated → the FP/FN-arm split), the non-generative-disposer positioning, the C-category targeting, and the M4 safety quarantine. The curated version is **paper Appendix B (Design Provenance)**.

---

## Ethos (why §6 of the paper is empty on purpose)

We aim for truth, not for fabricated expectations — that is the entire point of what we are building. The paper's Results section is **intentionally empty** until experiments E1–E4 actually run, and every claim is tagged in the paper's Claims Ledger (`architectural` / `prior-work` / `under-test` / `pending-evidence`). The same evidence gate the engine imposes on findings, we impose on our own paper.

So, in this project's vocabulary:

- A **detected false positive** is a *good* sign, not a failure — at the proposal stage it is the over-proposing recall layer doing its job (a cost line, never a credibility line; the gate rejects it), and in the single-stage baseline it is the trap reproducing as expected, which *validates* the comparison.
- An **unflattering metric** is a finding, not a thing to bury. If the gate leaks (`Prec_gate < 1`), or the raw proposal already flips cleanly, or proposer recall turns out flat across the gap — each is a real, publishable result.
- A **"trap"** is what we exist to prevent; naming it precisely is how we escape it. Writing optimistic results before the evidence lands would be the Semantic Trap one level up, and we don't do it.

---

*Index only. Source of truth: `propose-dispose-paper.md` (science) and `.agents/specs/` (execution).*
