# Resolution Report — propose-dispose-validation

## Header

```
spec_id:          propose-dispose-validation
final_status:     approved
cycle_started:    2026-07-24T07:00:00Z
cycle_closed:     2026-07-24T16:50:00Z
rounds:           1
arbiter_invoked:  false
```

---

## Participants

- **producer:** claude-sonnet-4-6 (Nyx / Eragon PM session)
- **validator:** claude-opus-4-6 (Eragon, parallel validation session)
- **arbiter:** n/a

---

## Outcome Summary

The `propose-dispose-validation` spec (F-PD-B) was implemented and validated in a single round with no conflicts. All completable deliverables across TG0–TG5 are confirmed: the M0 walking skeleton flips cleanly on CVE-2024-7041, all four funnel metrics are cross-checked, the 10-pair B-V2P corpus is smoke-tested and power-sufficient, the live E2 result independently reproduces (b=10, c=0, H2a confirmed at p=0.0044 via external haiku producer), and the locus-1 guardrail (TG4 PBT: M4 production-off + gate neutrality) passes cleanly. ARCH #20 funnel auto-registration fix is verified via 9 dedicated PBT tests. Full test suite: 568 passed, 4 skipped, 0 failures.

Two minor issues from the verdict: Issue 1 (completion report E3 −Control value — artifact is correct, report transcription was misread by validator; no actual error in report) is resolved as a non-issue. Issue 2 (DEV-6 pre-registration DRAFT status) is a standing operator action — lock `E2-preregistration.md` before any future E2 extensions. The paper correctly frames the live E2 result as exploratory. No operator escalations are open beyond the pre-registration lock.

---

## Artifact Index

- **Final completion report:** `.agents/specs/propose-dispose/specs/propose-dispose-validation/validation/completion-report.md`
- **Final verdict:** `.agents/specs/propose-dispose/specs/propose-dispose-validation/validation/verdict.md`
- **Arbiter audit:** n/a (single-round clean approval)
- **Key implementation artifacts:**
  - `strix/research/corpus.py` — 10-pair B-V2P corpus + `power_check`
  - `strix/research/metrics.py` — read-only funnel metrics
  - `strix/research/ablation/single_stage.py` — M4 ablation (sentinel-gated, off in prod)
  - `strix/report/state.py` — ARCH #20 funnel auto-registration fix
  - `tests/test_bv2p_corpus.py` — 27 per-pair exploitability tests
  - `tests/test_funnel_emit_hook.py` — 9 ARCH #20 PBT tests
  - `tests/test_single_stage_ablation.py` — M4 production-off + gate-neutrality PBTs
  - `benchmarks/bv2p/{8 new pairs}/` — Docker fixtures (VULN_MODE switch)
  - `artifacts/e1_tradeoff.{csv,json}` — H1 confirmed (pilot)
  - `artifacts/live_experiment_results.json` — H2a live, b=10, c=0, p=0.0044
  - `artifacts/e3_ablation.{csv,json}` — H3 directional (pilot)
  - `artifacts/e4_perturbation.{csv,json}` — H4 confirmed (pilot)
  - `artifacts/m0_results.json`, `artifacts/m1_cross_check.json`
  - `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` — paper draft

---

## Standing Operator Action

**DEV-6 — Pre-registration lock required before next E2 run:**
- File: `.agents/specs/propose-dispose/specs/propose-dispose-validation/planning/E2-preregistration.md`
- Action: set `Status: LOCKED`, fill `[LOCK: name]`, `[LOCK: YYYY-MM-DD]`, `[LOCK: git sha]`
- Constraint: must be done before any future E2 run claims its result as pre-registered and confirmatory. The current live result (p=0.0044) stands as a valid exploratory finding.

---

## Lessons for Future Specs

1. **Pre-registration timing is hard at research-track speed.** The corpus, harness, and pre-registration document should be committed in a single atomic commit — corpus-frozen commit hash is what goes in the `[LOCK: git sha]` field. Future research specs should make this a Gate 4 checkpoint before data is unblinded.

2. **DEV split between WAF-blocked provider and fallback is valid but must be surfaced immediately.** When `agentrouter` was WAF-blocked, the producer correctly fell back to OpenRouter/haiku and documented it. The correction in `d377423` (replacing hardcoded model strings with module-level constants) is the right approach — implementation provenance must be runtime-accurate, not hardcoded to the planned provider.

3. **E1/E3/E4 as pilot (static proxy) is an honest and valid framing.** Using a deterministic baseline for the tradeoff and ablation experiments while reserving live LLM calls for the primary McNemar test (E2) concentrates API spend on the highest-validity result. Future research specs should document this split explicitly in the tasks.md from the start.

4. **ARCH #20 (funnel auto-registration) closes a subtle `C ⊆ P` gap.** Direct-filer harness paths that called `record_harness_run` without a prior ProposalRecord would silently violate the gate-neutrality invariant at the data layer. The fix (auto-synthetic `ProposalRecord`) preserves the invariant without changing gate logic — and the 9 new PBT tests make it regression-proof. This pattern (defend invariants at the data-write layer, not only in gate logic) is worth encoding for future disposer extensions.

5. **Completion report §B transcription errors don't block approval when artifacts are correct.** The E3 −Control value discrepancy (report vs. artifact) was a validator misread — the report was correct. Future completion reports benefit from copy-pasting numbers directly from artifact JSON rather than summarizing.
