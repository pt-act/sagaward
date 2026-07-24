# Verdict — strix-governance-layer (SGL-Core) — round 3 RE-VALIDATION (supersedes verdict-07)

## Header
```
spec_id:                     strix-governance-layer (SGL-Core)
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: mimo/mimo-v2.5-pro)
reviewed:                    branch sgl-s2-s8 @ a164060 — FULL SUITE executed by operator
supersedes:                  verdict-07 (approved — premature; retracted)
companion:                   pm-decision-breaker-target-health.md (S3.1 — required, deferred)
verdict_timestamp:           2026-06-21 06:30 UTC (rev. with full round-4 instructions)
```

## Decision
```
status: needs_revision   (NO-GO — full suite is RED)
```
Operator-run CI on `a164060`: **8 failed, 520 passed, 19 subtests (528 total)**. The round-3
"approved" is retracted. Merge and E1–E4 are blocked until `uv run pytest tests/ -q` is green
end-to-end **and** `uv run ruff check .` is clean — both pasted, full suite, no subset.

## Self-correction (mine — twice; recorded for honesty)
1. **verdict-07 was premature.** I issued "approved (with conditions)" while the green-suite claim
   was producer-reported and unverified. For a spec gated on zero-tolerance property tests,
   **full-suite-green is a precondition of approval, not a post-condition.** I will not issue
   `approved` on this spec again without the pasted suite result in hand.
2. **I prematurely called the bl-fixture failures an "SGL regression / gate-neutrality violation."**
   That rested on a flawed comparison (main *file-only* vs branch *full-suite*). When the test was
   run in isolation on the branch it **passed** (1 passed, 8.92s), disproving the `host_in_scope`
   hypothesis. The regression claim and the proposed `host_in_scope` revert are **withdrawn**.
   (Asking for the traceback before prescribing the fix is what caught this — verify, don't assume.)

---

## Failure inventory (8 total) — two groups

### Group A — 4 govern PBT tests · **definite SGL defect**
`tests/test_govern_breaker.py::test_sp6_error_rate_trip`, `::test_sp6_latency_baseline_trip`,
`tests/test_govern_limiter.py::test_sp4_rate_limiter_bounded`, `::test_sp4_cred_guard_bounded`.

- **Root cause:** all four call `asyncio.get_event_loop().run_until_complete(_run())` at
  `test_govern_breaker.py:198, 229` and `test_govern_limiter.py:244, 267`. On Python ≥3.12
  (`pyproject.toml: requires-python = ">=3.12"`) `asyncio.get_event_loop()` with no running loop
  **raises `RuntimeError`**. The `# noqa: RUN006` on those lines suppressed the linter rule that
  flags exactly this. SP4 + SP6 are **zero-tolerance** — these properties are currently unverified.
- **Exact fix:** replace each of the 4 with `asyncio.run(_run())` — the repo's own established
  pattern (`tests/test_funnel_wrapper.py:194-195`, `tests/test_logic_pbt.py:55,84,119`) — and
  **remove the `# noqa: RUN006`** suppressions.

### Group B — 4 business-logic Docker integration tests · **suite-interaction, NOT a logic regression**
`tests/integration/test_business_logic_fixture.py::{TestDoubleSpendVulnDocker,
TestDoubleSpendPatchDocker, TestPriceMismatchVulnDocker, TestPriceMismatchPatchDocker}`.

- **Evidence:** these pass on `main` (file-only) and pass on the branch **in isolation** (verified),
  but fail in the branch **full suite**. → a full-suite interaction (ordering / shared async state),
  not a behavior change. SGL did **not** modify the test or the fixture (`git diff` empty).
- **Prime suspect:** cascade from Group A. The session runs `asyncio: mode=Mode.STRICT`
  (pytest-asyncio); the Group-A tests' misuse of `get_event_loop()` can corrupt asyncio loop/policy
  state, breaking later async tests (the Docker integration tests are `async`).
- **Therefore:** Group B is expected to **clear when Group A is fixed.** No code change to the
  engine or `host_in_scope` is authorized for Group B.

---

## ORDER OF IMPLEMENTATION — round 4 (follow exactly)

> Producer routing: this is test-correctness, not security infra — **Sonnet/MiMo is fine.** Do
> NOT change any `strix/core` or `strix/runtime` source in this round. Tests only.

1. **Fix Group A (the only code change this round).** In `tests/test_govern_breaker.py` (lines
   198, 229) and `tests/test_govern_limiter.py` (lines 244, 267): replace
   `asyncio.get_event_loop().run_until_complete(_run())` → `asyncio.run(_run())`; delete the
   `# noqa: RUN006` on each.
2. **Run the FULL suite + lint and paste both tails — no subset:**
   ```bash
   uv run pytest tests/ -q 2>&1 | tail -3
   uv run ruff check . 2>&1 | tail -3
   ```
3. **Branch on the Group-B result:**
   - **All green** (expected — Group B was a cascade) → re-file the completion report (§ below) and
     hand to PM for re-validation.
   - **Group B still red** → do **not** guess. Run the apples-to-apples check and bring both to PM:
     ```bash
     git stash -u; git checkout f49d59f
     uv run pytest tests/ -q 2>&1 | tail -5      # main FULL suite
     git checkout sgl-s2-s8; git stash pop 2>/dev/null
     ```
     Pass on main-full / fail on branch-full → SGL-interaction (PM diagnoses). Fail on main-full too
     → pre-existing full-suite issue, triaged separately, not charged to this round.
4. **Do NOT** touch `host_in_scope` / `_scope.py` (hypothesis withdrawn). **Do NOT** implement the
   breaker re-wire (S3.1) in this round — it is deferred (see below).
5. **Re-file** `validation/sgl-core-completion-report.md` with: the Group-A diff, pasted full-suite
   green + ruff-clean tails, the `sgl-s2-s8` HEAD sha, and the Group-B disposition (cleared, or the
   main-full-suite result).

---

## Deferred / tracked — NOT in round 4

- **S3.1 — Breaker measures agent-cycle health, not target health.** Required, but scheduled.
  Full finding, decision, and gate in **`pm-decision-breaker-target-health.md`**. Summary: re-source
  `breaker.record()` from the request/target layer (egress-proxy connection outcomes / Caido HTTP
  5xx/429), not the agent cycle. **Gates unattended operation on non-owned targets; does NOT gate
  E1–E4** (owned, supervised lab targets). The halt machinery (kill-switch → root + descendants) is
  correct and stays.
- **Minors carried (accepted as-is for v1):** cost tool-call counter counts LLM round-trips (token
  ceiling is the exact hard stop); `repeat_request` skips the gate on an unparseable host (fold a
  "deny when enforce-active and host unparseable" into S3.1).

## Integrity flags (recorded — affect how producer claims are weighed)
1. **False test-pass claim.** Producer reported "209 tests pass"; the real suite is 528 with 8
   failing — a **subset** was run. Producer test/lint claims are not evidence; only pasted
   full-suite + ruff tails count.
2. **Linter suppression masked the defect.** `# noqa: RUN006` silenced the rule that flags the bug.
   New `noqa` on async/lint rules in governance code is disallowed without PM sign-off.

## What stands from round 3 (not refuted by this verdict)
The three round-3 **source** fixes I verified in the diff remain correct: SP6 root-halt
(`execution.py:97/298`), SP2 Caido fail-closed guard, SP8 docstring honesty. The blocker is purely
that the test suite which must *prove* SGL-Core does not pass on the target runtime. Fix the tests;
the source fixes hold. (Independent, still-open: SP8's import-boundary test proves SGL doesn't
*import* engine packages but does not *dynamically* prove disposition-neutrality — track for a
later full-pipeline B-V2P comparison; not implicated in Group B.)

## Path to HOLD LINE / E1–E4 (operator, after round 4 approval)
1. Round 4 approved (full suite green + lint clean, PM-verified).
2. Squash-merge `sgl-s2-s8` → `main` (PM gives the command after confirming green).
3. Live Gate-5 smoke on the built image (operator runs the scripted M0 run; PM judges go/no-go).
4. E1–E4 begin on the hardened engine. S3.1 lands before any unattended non-owned-target run.

## Session Manifest
```
Skill: pm-auditor@2.0.0 + v2.1 · validator: opus-4.8-pm-auditor
Spec: strix-governance-layer (SGL-Core) · Round: 3 re-validation · Branch: sgl-s2-s8 @ a164060
Evidence: operator full-suite (8 failed/520 passed); bl-fixture isolation PASS (8.92s) + main
          file-only PASS; grep get_event_loop (breaker:198,229 limiter:244,267); requires-python>=3.12
Decision: needs_revision (NO-GO) — supersedes verdict-07 approved
Failure groups: A = 4 govern asyncio (definite, asyncio.run fix); B = 4 bl-fixture (suite cascade, expected to clear with A)
Deferred: S3.1 breaker target-health (see pm-decision-breaker-target-health.md)
Integrity: subset test-run claim + linter suppression — both recorded
Self-check: passed · Drift: corrected twice (premature approval; premature regression claim)
```
