# Verdict — propose-dispose-validation — round 2

## Header

```
spec_id:                          propose-dispose-validation
validator:                        claude-opus-4-6 (Eragon, parallel validation session)
validator_distinct_from_producer: true   # producer = claude-sonnet-4-6
reviewed_completion_report:       completion-report-r2.md
verdict_timestamp:                2026-07-25T05:30:00Z
round:                            2
```

---

## Decision

**status: approved**

---

## Round 2 Scope

This round validates the deltas from round 1:
1. **E1, E3, E4 moved from pilot (static proxy) to live** — real haiku API calls + Docker containers
2. **Corpus expanded from 10 to 13 pairs** — 3 new real CVEs added (CVE-2026-59225, CVE-2026-59217, CVE-2026-59221)
3. **E2 rerun on 13-pair corpus** — b=13, c=0, p=0.0009 (was b=10, c=0, p=0.0044)
4. **Paper corrected** — all stale n=10/b=10/pilot references updated
5. **New deviation DEV-7** — path_traversal_proxy FN edge case documented

Round 1 items not affected by round 2 (TG0–TG4 software, M4 PBT, gate-neutrality) are not re-verified — they passed in round 1 and no code changes touched them.

---

## Per-Criterion Assessment (round 2 deltas only)

### E1 (H1) — Tradeoff Break — NOW LIVE

- **Producer's claim:** met (live haiku + Docker, n=13)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e1_live.json`
  - Producer: `anthropic/claude-haiku-4-5 via https://openrouter.ai/api/v1`
  - Timestamp: `2026-07-25T04:39:31Z`
  - Conservative: R_prop=0.462, Prec_gate=1.000, M4_recall=0.308
  - Moderate: R_prop=0.923, Prec_gate=1.000, M4_recall=0.769
  - Aggressive: R_prop=1.000, Prec_gate=1.000, M4_recall=1.000
  - **Prec_gate=1.000 at all three aggressiveness levels** — H1 confirmed
- **Notes:** The live result is more informative than the pilot. At conservative aggressiveness, haiku proposes on only 6/13 pairs (R_prop=0.462) — the FN arm is visible. At aggressive, all 13 are proposed and confirmed. Prec_gate never moves. This is the structural claim working as designed.

### E2 (H2a/H2b) — Gap-Dictation — EXPANDED CORPUS

- **Producer's claim:** met (n=13, b=13, c=0, p=0.0009; FN-arm b=0, c=1)
- **Validator's finding:** confirmed — independently re-verified
- **Evidence reviewed:** `artifacts/live_experiment_results.json`
  - 13 pairs, all `gap_class: small`
  - FP-arm: independently computed b=13, c=0 ✅ (matches JSON)
  - FN-arm: independently computed b=0, c=1 ✅ (matches JSON)
  - FN edge case: `openwebui-path-traversal-proxy` — `strix_fn_arm_correct=False` due to FastAPI/Starlette URL normalisation eating the double-encoded traversal path before the app handler. Documented as DEV-7.
  - Chi2 (continuity-corrected): (|13-0|-1)²/13 = 144/13 ≈ 11.077 ✅ (matches)
  - p=0.0009 from runner ✅
  - **H2a confirmed at p<0.001 — stronger than round 1**

### E3 (H3/H3b) — Intervention Ablation — NOW LIVE

- **Producer's claim:** met (honest null result — R_prop=1.0 all conditions)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e3_live.json`
  - All 4 conditions (full, no_control, no_knowledge, no_checklist): R_prop=1.000, Prec_gate=1.000, R_e2e=1.000, n=13
  - **H3 null result (honest):** haiku-4-5 proposes on all 13 pairs regardless of which context flags are toggled. The recall-reduction effect is underpowered at n=13 with this model.
  - **H3b confirmed:** Prec_gate=1.000 in all conditions — harness owns precision regardless of proposer-side context.
- **Notes:** The null H3 result is informative: it means haiku is capable enough to identify all 13 vulnerability classes from minimal endpoint description alone. The effect predicted by H3 requires harder pairs or a weaker model. This is honestly reported in §6.5 of the paper.

### E4 (H4) — Perturbation Invariance — NOW LIVE

- **Producer's claim:** met (strix 0 flips, M4 2 flips)
- **Validator's finding:** confirmed
- **Evidence reviewed:** `artifacts/e4_live.json`
  - 5 pairs × 4 non-baseline perturbations = 20 trials
  - strix_flip_count=0 (0/20) ✅
  - M4_flip_count=2 (2/20) — both on `flowise-ssrf-http-node` (`reword_cve` + `minimal_surface`)
  - H4_confirmed=True
  - **H4 confirmed:** Harness verdict is structurally invariant under surface perturbations.

### Corpus — Expanded to 13 Pairs (5 Real CVEs)

- **Producer's claim:** 3 new real CVE pairs added
- **Validator's finding:** confirmed
- **Evidence reviewed:**
  - `strix/research/corpus.py` — 13 pairs registered
  - New fixtures on disk: `benchmarks/bv2p/bfla_arena_model/`, `bfla_kb_upload/`, `path_traversal_proxy/` — each contains `Dockerfile`, `app.py`, `core.py`
  - CVEs: CVE-2026-59225 (BFLA arena model), CVE-2026-59217 (BFLA KB upload), CVE-2026-59221 (path traversal decode bypass) — all from open-webui, genuine public CVEs with GHSA advisories
  - 577 tests pass (was 568), 0 failures — 9 new corpus tests for the 3 new pairs

### Paper — Stale Values Corrected

- **Producer's claim:** all stale n=10/b=10/pilot references updated
- **Validator's finding:** confirmed with automated sweep
- **Evidence reviewed:** Automated checks confirm:
  - No `10/10`, `0/10`, `b=10` references remain in paper ✅
  - `b=13`, `n=13`, `χ²=11.077`, `p≈0.0009` all present ✅
  - E1 live numbers (R_prop=0.462/0.923/1.0) match artifact exactly ✅
  - H2b correctly shows `c=1` (path_traversal FN) ✅
  - 5 real CVEs listed (CVE-2026-59225, CVE-2026-59217, CVE-2026-59221 + original 2) ✅
  - No "pilot" or "simulation-derived" labels on E1/E3/E4 ✅
  - E4 table: 0/20 strix flips, 2/20 M4 flips — matches artifact ✅
  - §6.5 threat note: n=13, honest null for H3 ✅
  - Future work: synthesized ratio corrected to 8/13 ✅

---

## Deviations Audit

### DEV-2 (E1/E3/E4 pilot) — RESOLVED ✅
- Round 1: E1/E3/E4 used deterministic static proxy (no LLM, no Docker)
- Round 2: all four experiments use real haiku API calls against live Docker containers
- Artifact timestamps confirm real API calls: E1 at 04:39, E3 at 03:56, E4 at 04:44 (2026-07-25)

### DEV-6 (Pre-registration not locked) — STILL OPEN
- `planning/E2-preregistration.md` still shows `Status: DRAFT`
- E2 result (now p=0.0009) observed before lock
- Paper correctly frames as exploratory
- **Standing action: producer locks before any future E2 extension is claimed as confirmatory**

### DEV-7 (NEW) — path_traversal_proxy FN — ACKNOWLEDGED
- FastAPI/Starlette URL normalisation eats double-encoded traversal before app handler
- Impact: 1 FN in E2 FN-arm (b=0, c=1). FP-arm unaffected (b=13, c=0)
- Documented in paper §4.2 H2b section ✅
- Backlog item PD-VAL-7 proposed ✅

---

## Test Suite

- **Independent run:** `uv run pytest tests/ -q` → **577 passed, 4 skipped, 19 subtests, 0 failures** ✅
- Delta from round 1: +9 tests (3 new corpus pairs × 3 tests each)

---

## Issues Found

### Issue 1
- **Severity:** cosmetic
- **Location:** Paper footer / metadata
- **Description:** Paper footer still references `568 passed` test count from round 1. Should be `577`.
- **Suggested remedy:** Update paper footer test count.

### Issue 2
- **Severity:** cosmetic
- **Location:** `completion-report-r2.md` §A table
- **Description:** E2 row says `b=10, c=0, p=0.0044` for round 1 state — correct, but the `live_experiment_results.json` on disk now contains the n=13 result (overwritten). The round 1 raw JSON is not preserved separately.
- **Suggested remedy:** Note in resolution report. The round 1 result is documented in the round 1 completion report and verdict, and the git history preserves the original JSON.

No blocker or major issues.

---

## Verdict Rationale

All round 2 deltas verified. The critical gap from round 1 — E1/E3/E4 running against a static proxy simulation instead of real LLM + Docker — is fully resolved. All four experiments now use `anthropic/claude-haiku-4-5` via OpenRouter against live Docker containers, verified by artifact timestamps and producer/model metadata in the JSON files. The corpus expansion to 13 pairs (5 real CVEs) strengthens the E2 result from p=0.0044 to p=0.0009, and the 3 new real-CVE fixtures are independently confirmed on disk.

The paper is now consistent with all artifacts — no stale n=10/b=10/pilot references remain. One new deviation (DEV-7, path_traversal FN edge case) is documented honestly in both the completion report and the paper. DEV-6 (pre-registration lock) remains open as a standing producer/operator action.

Two cosmetic issues (paper footer test count, round 1 JSON overwrite). Zero blocker or major issues → **approved**.
