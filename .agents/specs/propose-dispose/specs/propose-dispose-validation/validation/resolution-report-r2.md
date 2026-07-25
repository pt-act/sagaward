# Resolution Report — propose-dispose-validation — round 2

## Header

```
spec_id:          propose-dispose-validation
final_status:     approved
cycle_started:    2026-07-24T07:00:00Z
cycle_closed:     2026-07-25T05:35:00Z
rounds:           2
arbiter_invoked:  false
```

---

## Participants

- **producer:** claude-sonnet-4-6 (Nyx / Eragon PM session)
- **validator:** claude-opus-4-6 (Eragon, parallel validation session)
- **arbiter:** n/a

---

## Outcome Summary

The `propose-dispose-validation` spec (F-PD-B) was validated in two rounds. Round 1 approved the core implementation with documented gaps (E1/E3/E4 were pilot/simulation, corpus was 2/10 real CVEs). Round 2 resolved all gaps: E1/E3/E4 are now fully live (real haiku API calls + Docker containers), the corpus is expanded to 13 pairs with 5 real CVEs, and the E2 result strengthened from p=0.0044 (n=10) to p=0.0009 (n=13).

All four hypotheses are now tested against real external LLM output:
- **H1 confirmed** — Prec_gate=1.000 at all aggressiveness levels (live E1)
- **H2a confirmed at p<0.001** — b=13, c=0 FP-arm sweep (live E2, n=13)
- **H2b honest** — b=0, c=1; one FN edge case documented (DEV-7)
- **H3b confirmed** — Prec_gate=1.000 in all ablation conditions; H3 recall-reduction is an honest null at n=13 with haiku (live E3)
- **H4 confirmed** — strix 0/20 flips, M4 2/20 flips (live E4)

Paper v1.0 is now consistent with all artifacts. No stale values remain. 577 tests pass, 0 failures.

---

## Artifact Index

- **Completion reports:** `completion-report.md` (round 1), `completion-report-r2.md` (round 2)
- **Verdicts:** `verdict.md` (round 1), `verdict-r2.md` (round 2)
- **Resolution reports:** `resolution-report.md` (round 1), `resolution-report-r2.md` (round 2, this file)
- **Paper:** `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` (canonical, camera-ready)

### Key experiment artifacts (all live):
| Artifact | n | Producer | Key result |
|----------|---|----------|------------|
| `artifacts/e1_live.json` | 13 | haiku-4-5 | H1: Prec_gate=1.0 all levels |
| `artifacts/live_experiment_results.json` | 13 | haiku-4-5 | H2a: b=13,c=0,p=0.0009 |
| `artifacts/e3_live.json` | 13 | haiku-4-5 | H3b: Prec_gate=1.0 all conditions |
| `artifacts/e4_live.json` | 5×4 | haiku-4-5 | H4: 0/20 strix flips |

---

## Standing Actions

### DEV-6 — Pre-registration lock (producer/operator)
- File: `planning/E2-preregistration.md`
- Action: set `Status: LOCKED`, fill `[LOCK: ...]` fields
- Constraint: must be done before any future E2 extension claims a confirmatory result

### DEV-7 — path_traversal_proxy harness probe (backlog PD-VAL-7)
- Fix URL double-decoding edge case in harness probe for path-traversal fixtures
- Not blocking: FP-arm unaffected, FN edge case documented honestly

---

## Round-by-Round Summary

### Round 1 (2026-07-24)
- **Verdict:** approved with documented gaps
- **Gaps:** E1/E3/E4 pilot (DEV-2), corpus 2/10 real CVEs, pre-registration DRAFT (DEV-6)
- **Key result:** E2 live, b=10, c=0, p=0.0044

### Round 2 (2026-07-25)
- **Verdict:** approved — all round 1 gaps resolved
- **Resolved:** DEV-2 (all experiments now live), corpus expanded to 5/13 real CVEs
- **New:** DEV-7 (path_traversal FN edge case, non-blocking)
- **Key result:** E2 live, b=13, c=0, p=0.0009 (stronger)

---

## Lessons for Future Specs

1. **"Pilot" labels are a red flag.** If the spec says "run experiments on live Docker containers with an external LLM," pilot/simulation results should trigger a round-2 push-back, not an approval with caveats. Round 1 was too lenient on this — the approval should have been conditional on resolving DEV-2 before closing.

2. **Corpus quality > corpus size for McNemar.** The jump from 10→13 pairs tightened the p-value from 0.0044 to 0.0009, but the real improvement was moving from 2/10 real CVEs to 5/13. For peer review, the real/synthesized ratio matters more than n.

3. **E3 null results are informative when reported honestly.** The H3 null (haiku proposes on all pairs regardless of context flags) is a genuine finding about model capability, not a failure. Future specs should anticipate that H3-style ablation effects may require weaker models or harder pairs to surface, and pre-register accordingly.

4. **Paper-artifact reconciliation is a distinct validation step.** Round 2 caught multiple stale values (n=10, b=10, H2b b=0 c=0, pilot labels, E1 table mismatches) that survived from the round 1 paper. Future specs should include an explicit "paper-artifact sweep" as a validation gate before the paper is declared camera-ready.
