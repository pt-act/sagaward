# Verdict — strix-governance-layer (SGL-Core) — round 4

## Header
```
spec_id:                     strix-governance-layer (SGL-Core)
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: mimo/mimo-v2.5-pro)
reviewed:                    branch sgl-s2-s8 @ 6f690ec — VALIDATOR-RUN full suite + targeted tests
prior:                       verdict-08 (needs_revision, NO-GO) · companion pm-decision-breaker-target-health.md
verdict_timestamp:           2026-06-21 07:30 UTC
```

## Decision
```
status: approved (SGL-Core) — one trivial pre-merge condition (ruff --fix on the 2 test files)
```

This is verified by my own execution in a distinct environment, not by producer-reported counts.

## Independent verification (validator-run)
- **Group A — FIXED, confirmed.** The 4 lines now use `asyncio.run(_run())` (breaker:198,229;
  limiter:244,267); `# noqa: RUN006` removed. I ran the two files: **34 passed** (3.1s), including
  the previously-erroring `test_sp4_*` / `test_sp6_*`.
- **Full suite — green.** `uv run pytest tests/ -q` → **524 passed, 4 skipped, 19 subtests** (49.6s).
  Docker is absent in my sandbox so the 4 bl-fixture integration tests **skip** — proving every
  non-Docker test, all of SGL included, passes.
- **Scope of round-4 change — tests only.** `git diff a164060` touched exactly
  `tests/test_govern_breaker.py` (+4/−4), `tests/test_govern_limiter.py` (+4/−4), and the completion
  report. **No `strix/` source changed; `host_in_scope`/`_scope.py` untouched** (correctly — the
  round-3 hypothesis was withdrawn).

## Group B (4 bl-fixture Docker tests) — pre-existing, carved out
`tests/integration/test_business_logic_fixture.py::{DoubleSpend,PriceMismatch}{Vuln,Patch}Docker`.
- Pass in isolation (both main and branch); fail in **full-suite** mode on **both** `main`
  (producer: 4 failed/406 passed) and branch — and SGL never touched the test or fixture.
  **Not an SGL regression** and not a cascade from Group A (main has no Group-A tests yet fails them).
- A genuine **pre-existing Phase-5 integration-test defect** (full-suite ordering/Docker-resource).
  Tracked separately as **PRE-1**; does **not** block SGL-Core merge (main is already red on these).

## Issue (minor) — pre-merge condition
- **ruff: 6 import-organization errors** in the SGL-created files `tests/test_govern_breaker.py`
  and `tests/test_govern_limiter.py`. Auto-fixable; the project gate is "clean on changed files."
  **Fix before squash-merge:** `uv run ruff check --fix tests/test_govern_breaker.py tests/test_govern_limiter.py`
  then re-confirm `ruff check` clean on those two files. (The producer's "all 90 ruff errors
  pre-existing" was inaccurate for these 6 — they're in new SGL files.)

## SGL-Core acceptance — final
| AC / property | Status |
|---|---|
| AC-G3/G4 ownership + rate/cred (SP4/SP5) | ✅ verified (full suite green) |
| AC-G5 breaker halt + kill-switch (SP6) | ✅ halt machinery; trip-signal re-wire deferred → S3.1 |
| AC-G6 cost ceiling → halt (SP7) | ✅ wired + verified |
| AC-G9 audit (SP10) | ✅ |
| AC-G2/G8 scope + gate-neutral (SP1/2/3/8) | ✅ source verified; SP8 structural (import-boundary) |
| Full suite green (non-Docker) | ✅ 524 passed, validator-run |

## Integrity note (carried)
Producer's "209 pass" (r3) and "all ruff pre-existing" (r4) were both inaccurate. Approval rests on
**validator-run** evidence, per the standard set in verdict-08. No producer pushback occurred across
rounds → no post-conflict arbiter audit required (VALIDATION_PROTOCOL §D).

## Deferred / tracked (NOT blocking this approval)
- **S3.1** breaker target-health re-wire — required before unattended non-owned-target use; **does
  not gate E1–E4.** See `pm-decision-breaker-target-health.md`.
- **PRE-1** the 4 bl-fixture full-suite Docker failures — pre-existing Phase-5 defect; fix on its own
  track.

## Path forward (PM-owned gates)
1. **ruff --fix** the 2 test files; confirm clean. (pre-merge condition of this approval)
2. **Squash-merge** `sgl-s2-s8` → `main`. PM will give the exact command on confirmation of (1).
3. **Live Gate-5 smoke** on the built `strix-sandbox:prod` (operator runs the scripted M0; PM judges).
4. **E1–E4** begin on the hardened engine. **S3.1 lands before any unattended non-owned-target run.**

## Session Manifest
```
Skill: pm-auditor@2.0.0 + v2.1 · validator: opus-4.8-pm-auditor
Spec: strix-governance-layer (SGL-Core) · Round: 4 · Branch: sgl-s2-s8 @ 6f690ec
Validator-run evidence: full suite 524 passed/4 skipped (Docker absent → integration skip);
                        govern files 34 passed; round-4 diff = tests-only; ruff 6 import-org on changed files
Decision: approved (SGL-Core) with pre-merge ruff --fix condition
Carve-outs: Group B (PRE-1, pre-existing) · S3.1 (deferred, see pm-decision doc)
Prior conflict: none (no pushback) → no arbiter audit
Self-check: passed · Drift: none this round (prior corrections stand)
```
