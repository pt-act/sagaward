# Completion Report — propose-dispose-validation (F-PD-B) — round 2

## Header

```
spec_id:        propose-dispose-validation
feature:        F-PD-B (type: research, non-gating)
producer:       claude-sonnet-4-6 (Nyx / Eragon PM session)
round:          2 (supersedes round 1 on all changed items; round 1 artifacts remain for lineage)
started:        2026-07-25T01:00:00Z
completed:      2026-07-25T05:00:00Z
branch:         new
commits (this round, chronological):
  717c5d6  feat(research): live E1/E3/E4 experiments — haiku + Docker harness
  5b814d8  feat(research): E1/E3/E4 live LLM experiments — haiku via OpenRouter
  ac01643  feat(research): live E1/E3/E4 — real haiku API + Docker containers
  5807af0  feat(paper): E1/E3/E4 now fully live — remove pilot labels, update tables
  155ed54  feat(research): E1/E3/E4 live experiments on expanded 13-pair corpus (3 real CVEs added)
  31ef9dc  feat(research): expand corpus to 13 pairs (5 real CVEs) + live E1/E2/E3/E4 results
  36af62b  docs(validation): update completion report with n=13 E1/E2/E3/E4 live results
prior_reports:  completion-report.md (round 1 — 10-pair corpus, E1/E3/E4 pilot)
```

---

## §A — What Changed From Round 1

### Gaps addressed by this round

| Gap | Round 1 state | Round 2 state |
|-----|---------------|---------------|
| E1, E3, E4 experiments | pilot (deterministic static proxy, no LLM, no Docker) | live — real haiku API calls + Docker containers |
| Corpus real-CVE ratio | 2/10 (2 real, 8 synthesized) | 5/13 (5 real, 8 synthesized) |
| E2 on expanded corpus | b=10, c=0, p=0.0044 (10 pairs) | b=13, c=0, χ²=11.077, p=0.0009 (13 pairs) |
| Paper accuracy | stale pilot labels, stale b/c/p values, stale n, H2b wrong | all corrected; all four experiments fully live |

### New artifacts (round 2)

| Artifact | Path | Status |
|----------|------|--------|
| Live E1 results | `artifacts/e1_live.json` | ✅ |
| Live E3 results | `artifacts/e3_live.json` | ✅ |
| Live E4 results | `artifacts/e4_live.json` | ✅ |
| E1/E3/E4 live runner | `artifacts/run_live_e1e3e4.py` | ✅ |
| BFLA arena model fixture | `benchmarks/bv2p/bfla_arena_model/` | ✅ CVE-2026-59225 |
| BFLA KB upload fixture | `benchmarks/bv2p/bfla_kb_upload/` | ✅ CVE-2026-59217 |
| Path traversal proxy fixture | `benchmarks/bv2p/path_traversal_proxy/` | ✅ CVE-2026-59221 |
| Paper v1.0 (updated) | `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` | ✅ all stale values corrected |

---

## §B — Acceptance Criteria Self-Check (changed items only)

### TG5 — Experiments (updated)

**5.1 — E1 (H1): live result**
- **Claim:** met (now fully live — real haiku API calls + Docker containers, n=13)
- **Evidence:** `artifacts/e1_live.json`
  - Conservative: R_prop=0.462, Prec_gate=1.000, M4_recall=0.308
  - Moderate: R_prop=0.923, Prec_gate=1.000, M4_recall=0.769
  - Aggressive: R_prop=1.000, Prec_gate=1.000, M4_recall=1.000
  - **H1 confirmed:** Prec_gate=1.000 at all aggressiveness levels

**5.2 — E2 (H2a/H2b): expanded corpus**
- **Claim:** met (n=13, b=13, c=0, p=0.0009)
- **Evidence:** `artifacts/live_experiment_results.json`
  - **FP-arm:** b=13, c=0, χ²=11.077, p≈0.0009 — **H2a CONFIRMED (stronger)**
  - **FN-arm:** b=0, c=1, p≈1.000 — one `path_traversal_proxy` FN (harness probe edge case, URL double-decoding via FastAPI router)
  - Producer: anthropic/claude-haiku-4-5 via openrouter.ai (13 real API calls)

**5.3 — E3 (H3): live result**
- **Claim:** met (now fully live, honest null result)
- **Evidence:** `artifacts/e3_live.json`
  - All 4 conditions: R_prop=1.000, Prec_gate=1.000, R_e2e=1.000
  - **H3 null (honest):** haiku-4-5 proposes on all 13 pairs regardless of context flags — the recall-reduction effect is underpowered at n=13 with this model. H3b confirmed: Prec_gate=1.000 in all conditions.

**5.4 — E4 (H4): live result**
- **Claim:** met (now fully live)
- **Evidence:** `artifacts/e4_live.json`
  - strix_flip_count=0, M4_flip_count=2 (flowise-ssrf: `reword_cve` and `minimal_surface`)
  - **H4 confirmed:** strix verdict invariant; M4 flips on 2 perturbations

**2.1/2.2 — Corpus expanded to 13 pairs**
- **Claim:** met
- **Evidence:** `strix/research/corpus.py` — 13 pairs. 3 new real CVEs: CVE-2026-59225 (BFLA arena, `bfla_arena_model`), CVE-2026-59217 (BFLA KB upload, `bfla_kb_upload`), CVE-2026-59221 (path traversal, `path_traversal_proxy`). All fixtures build and flip. 577 tests pass.

---

## §C — Known Deviations (updated)

**DEV-2 — E1/E3/E4 pilot (RESOLVED)**
- Round 1 state: E1/E3/E4 used a deterministic static proxy simulation (no LLM, no Docker)
- Round 2 state: all four experiments now use real haiku API calls against live Docker containers
- **Resolved — no longer a deviation**

**DEV-6 — E2 pre-registration not locked (STILL OPEN)**
- Same status as round 1. E2 result (now p=0.0009) was observed before `E2-preregistration.md` was set to LOCKED. Result is valid as exploratory/live finding; cannot be claimed as pre-registered confirmatory.
- **Action:** producer sets `Status: LOCKED` before any future E2 extension is claimed as confirmatory.

**DEV-7 (NEW) — path_traversal_proxy FN on vuln side**
- `path_traversal_proxy` vuln container returned a URL double-decoding edge case: FastAPI's Starlette router normalised the double-encoded path (`%2F` → `/`) before the app-level handler saw it, so the harness probe did not trigger the traversal on the vuln side.
- **Impact:** one c=1 FN in the E2 FN-arm (b=0, c=1, p≈1.000). The FP-arm (b=13, c=0) is unaffected. The finding is reported honestly in §4.2 H2b.
- **Action:** harness probe for path traversal fixtures should use non-encoded traversal or a test that confirms the router bypass. Logged as PD-VAL-7.

---

## §D — State Management

### Quality Gates (updated)

| Gate | Status | Evidence |
|------|--------|----------|
| Gate 1 — design-principle alignment | PASS | Unchanged |
| Gate 2 — Tier-1 checks pass | PASS | 577 tests pass (was 568), 0 failures |
| Gate 3 — Tier-2 PBT: M4 production-off + gate neutrality | PASS | Unchanged |
| Gate 4 — research validity | PARTIAL → PARTIAL | Pre-registration still DRAFT (DEV-6). All four experiments now live (DEV-2 resolved). |

### Test count: 577 passed, 4 skipped, 0 failures (was 568)

### Backlog additions
- **PD-VAL-7** — Fix `path_traversal_proxy` harness probe for URL double-decoding edge case (FastAPI/Starlette normalises paths before app handler).

---

## §E — Handoff Notes

- **Gate:** `uv run pytest tests/ -q` → **577 passed, 4 skipped, 19 subtests, 0 failures**
- **Final E2 result:** b=13, c=0, χ²=11.077, p≈0.0009 (anthropic/claude-haiku-4-5 via openrouter.ai, 13-pair corpus, all small-gap)
- **All four experiments:** fully live — real haiku API calls + Docker containers
- **Paper:** all stale values corrected; no pilot labels remain; n=13 throughout
- **One standing operator action:** lock `E2-preregistration.md` (DEV-6) before any future E2 claimed as confirmatory
- **Commit log (this round):**
  ```
  36af62b  docs(validation): update completion report with n=13 E1/E2/E3/E4 live results
  31ef9dc  feat(research): expand corpus to 13 pairs (5 real CVEs) + live E1/E2/E3/E4 results
  155ed54  feat(research): E1/E3/E4 live experiments on expanded 13-pair corpus (3 real CVEs added)
  5807af0  feat(paper): E1/E3/E4 now fully live — remove pilot labels, update tables
  ac01643  feat(research): live E1/E3/E4 — real haiku API + Docker containers
  5b814d8  feat(research): E1/E3/E4 live LLM experiments — haiku via OpenRouter
  717c5d6  feat(research): live E1/E3/E4 experiments — haiku + Docker harness
  ```
