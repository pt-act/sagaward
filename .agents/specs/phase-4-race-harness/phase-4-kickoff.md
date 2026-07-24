# Phase 4 Kickoff — Locked Contracts + Coder Prompt

> Race Condition Harness (feature F4, primitives P1 + P2 reused). Feeds Phase 5; supplies the race B-V2P pairs for `propose-dispose-validation`.
> Source of truth: `.agents/specs/phase-4-race-harness/{spec.md,tasks.md}` (v1.1, PM-amended) + `manifest.yml`.
> Purpose: lock the dispatch/precondition/diff/verdict/tool contracts before coding, and record the four pre-kickoff amendments.

## Preconditions (verified)
- Phase 0/1/2/3 merged to `main`; Phase 3 squash-merged at `ce731a5 Phase 3 rebased (#6)`; `main` clean, full suite 225 green.
- Consumes: Phase 1 `identity_store` + `replay_engine` + `differential_engine` + `volatile_field_normalizer`; Phase 0 `impact_gate` (`strix/report/state.py`).
- Dispatch rides the Phase 1 replay send path: `caido_api.replay_send_raw` (async), `build_raw_request`, `apply_modifications`, `parse_raw_response`.
- **Branch from `main`** (it has Phase 0–3): `git checkout -b phase-4-race-harness main`. Do **not** stack on another phase branch.

---

## DECISIONS (amend the spec → folded into spec/tasks v1.1)

Four PM amendments are already integrated into `spec.md`/`tasks.md` v1.1; they are locked here so the reasoning is explicit:

1. **P2 reuse boundary (the load-bearing one).** P2 is the **pairwise** differ — it diffs baseline vs. post-action observable state into a state delta, and **nothing more**. The **commit count** across N copies is a **new, small Phase-4 aggregator** that counts over P2's output + the per-copy outcomes. It is **not** P2 and **not** a second differ. Do not extend P2 to count commits, and do not re-diff in the aggregator.
2. **Deterministic test target.** Every e2e race test (TG6.1/6.2) runs against a seeded target with an **artificially widened, deterministic check-then-mutate window** (e.g. an explicit server-side sleep between read and commit) so collisions reproduce **every run** — hermetic gates, not timing-flaky.
3. **Scope gate (F-11).** Before **any** fan-out, assert the target is in scope (`scope_rules`); out-of-scope → **refuse to dispatch** (zero requests sent). The harness mutates live state, so this gate is mandatory and precedes both dispatch and precondition setup.
4. **Bounded retry on inconclusive (F-7).** A no-collision trial retries from precondition up to a bounded **R** attempts (capped default) before finalizing *inconclusive*; retry count recorded.

**The 5 ∀ invariants are unchanged in spirit** — invariant #5 (scope-bounded dispatch) and the commit-count split are the only additions over the original four.

---

## Contract A — Precondition & Reset Manager (P1-backed) · `strix/core/race/` (new) reusing `strix/core/identity/`
- `setup(precondition, identity) -> baseline | Inconclusive` — drive the target to a declared precondition (e.g. `balance=100`, `token unused`, `coupon unredeemed`) on a **P1 identity**; record a **baseline** observable state **read as an HTTP response**.
- `reset()` — return to the declared precondition between independent trials **and between bounded retries**.
- Unreachable precondition → **`Inconclusive`** (never *safe*, never dropped). Per-target P1 identity only; no cross-target state.

---

## Contract B — Concurrency Dispatcher + scope gate · `strix/core/race/` reusing `caido_api`
- **Scope gate first (F-11):** `assert target ∈ scope_rules` → else `ScopedRefusal` (no requests sent).
- `dispatch(request_set, N, jitter, shared_session) -> list[CopyOutcome]` — fan out **exactly N** identical copies over `replay_send_raw` under `asyncio`, all carrying **one shared** P1 session (no per-copy auth divergence), join on all N.
- **Bounded** N (capped default); bounded **jitter** window (small default); rate-respecting — no unbounded loop, no DoS-shaped flooding. Jitter is a sensitivity knob, **never** a verdict input.
- Credentials redacted in copy logs / tool returns (inherited from P1).

---

## Contract C — Outcome Collector + P2 pairwise delta + commit-count aggregator · `strix/core/race/` reusing `strix/core/diff/` *(the amendment-1 split — keep it clean)*
- **Collect** every per-copy response (status, body, set-cookie) with **no drops**; parse via `parse_raw_response` into the differ's input shape.
- **Read post-action observable state as an HTTP response**; where no observable read exists, fall back to per-copy commit signals and **record the absence of an independent oracle** (lower confidence, never a fabricated verdict).
- **P2 pairwise delta (reused):** `diff(baseline, post_action) -> state_delta`. Same volatile-field normalizer. **Not extended to count.**
- **Commit-count aggregator (NEW, pure):** `count_commits(outcomes, state_delta) -> int` — reduces N outcomes + delta magnitude (e.g. balance dropped 3× a single redemption ⇒ 3) to a commit count. **Counts over P2's output only; no diffing here.**

---

## Contract D — Verdict + bounded retry + impact-gated evidence · `strix/core/race/` *(parallel: synthetic tuples)*
- `verdict(state_delta, commit_count) -> Race | Safe | Inconclusive` — **pure over (delta, count)**: count > 1 (or a delta inconsistent with one action) → **Race**; ≤ 1 / idempotent → **Safe**; no collision → **Inconclusive**. Timing **never** enters this function.
- **Bounded retry:** on `Inconclusive`, retry from precondition up to **R** (reset between attempts), record retry count; finalize *Inconclusive* only after R.
- **Impact-gating:** a `Race` is promotable to a finding **only** with the concrete before/after **state-delta diff** attached; **no diff → no report**.

---

## Contract E — F4 agent tool · `strix/tools/race/` (mirror `strix/tools/proxy` conventions)
- `@function_tool` `run_race_harness(request_set, precondition, N, jitter, retry_bound)` — `_ctx_client`, JSON returns.
- Returns: per-copy **outcome table** + P2 **state diff** + **commit count** + **verdict** (race/safe/inconclusive) + glass-box record (N, jitter, retry count, precondition, **scope decision**, the state read used).
- **WIRE IT INTO THE AGENT** — add the tool to `_BASE_TOOLS` in `strix/agents/factory.py` and add a **registration test** asserting it is present in the built agent. *(This is the Phase 3 gap: the inventory/OOB tools were defined but not wired — caught at close-out. Do not repeat it.)*

---

## Evidence model (extends Phases 1/2 — keep consistent, do NOT merge the two fields)
- **`evidence_class`** (strength, drives the gate): Phase 4 sets **`"race_result"`** — the value Phase 2's kickoff already anticipated. Enum is now `diff | callback | reachability | race_result | none`. **Add `race_result` to the impact-gate enum** (`strix/report/state.py`), the way Phase 1 added `diff` and Phase 2 added `callback`.
- **`artifact_type`** (media, SEPARATE field): Phase 4 adds **`"state_delta"`** (the before/after observable-state diff) to the existing `{semantic_delta, http_exchange, oob_callback}`. Renderers switch on `artifact_type`, the gate on `evidence_class`. **Do not merge them** — same rule as Phases 1/2.

---

## Build order (from tasks.md)
Critical path `TG2 precondition → TG1 dispatch(+scope) → TG3 collect+diff+count → TG5 tool → TG6 testing`; **TG4 verdict + commit-count aggregator develop in parallel against synthetic `(baseline, post-action, outcome)` tuples** (no live concurrency needed), mirroring how Phase 1 PBT'd its differ against synthetic response pairs. ~4.5 iterations. Gate per push: Tier-1 + the **3 PBT invariants** (single-use enforcement, detection determinism, no-side-effect-on-safe-target) + precondition-isolation (TG2 + TG6.3) + scope-bounded dispatch (TG1.7 + TG6.6), all exercised; ruff + changed-files `mypy --strict` + `bandit -r strix/ -c pyproject.toml`.

## Testing — pure cores + deterministic e2e, offline
Verdict and commit-count aggregator are pure → fixture/PBT them against synthetic tuples, never live races. The e2e double-redemption / idempotent tests run against a **seeded in-repo target with a deterministic widened check-then-mutate window** so they reproduce every run. Use `tempfile`/`tmp_path` for any trial-record fixtures — **never hardcoded `/tmp`** (Phase 3 hermeticity lesson; it made 3 tests non-hermetic).

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Phase 4 — Race Condition Harness, per .agents/specs/phase-4-race-harness/{spec.md,tasks.md} (v1.1,
PM-amended) and the locked contracts in this kickoff.

START ON A FRESH BRANCH: git checkout -b phase-4-race-harness main  (main has Phase 0-3; do NOT stack on
another phase branch).

FOUR AMENDMENTS (already in spec/tasks v1.1) — honor them:
1. P2 is the PAIRWISE differ ONLY (baseline vs post-action -> state delta). The commit count across N copies
   is a NEW small Phase-4 aggregator that counts over P2's output + outcomes — NOT P2, NOT a second differ.
2. Every e2e race test runs against a seeded target with an artificially widened, DETERMINISTIC
   check-then-mutate window (server-side sleep between read and commit) so collisions reproduce every run.
3. SCOPE GATE before any fan-out: assert target in scope_rules, else refuse to dispatch (zero requests sent).
4. BOUNDED RETRY on inconclusive: retry from precondition up to R (capped), reset between, record the count.

Build in critical-path order: TG2 precondition -> TG1 dispatch(+scope gate) -> TG3 collect+P2 diff+commit-count
-> TG5 tool -> TG6 testing; develop TG4 verdict + commit-count aggregator in parallel against synthetic
(baseline, post-action, outcome) tuples.

Honor the LOCKED interfaces exactly:
- Precondition manager (P1-backed): drive to declared precondition, baseline read AS AN HTTP RESPONSE; reset
  between trials AND retries; unreachable precondition -> Inconclusive (never safe, never dropped).
- Dispatcher: scope gate FIRST; fan out exactly N copies sharing ONE P1 session; bounded N + bounded jitter,
  rate-respecting, no flooding; jitter is sensitivity only, never a verdict input.
- Collector + diff + count: no dropped copies; post-action state read as HTTP; P2 produces the pairwise delta
  (reused, not extended); the NEW commit-count aggregator counts over outcomes + delta magnitude.
- Verdict: pure over (state_delta, commit_count); count>1 -> race, <=1/idempotent -> safe, no collision ->
  inconclusive (then bounded retry). Timing NEVER enters the verdict.
- Impact-gating: a race candidate is a finding ONLY with the before/after state-delta diff attached; no diff,
  no report.
- F4 tool: run_race_harness returns outcome table + P2 state diff + commit count + verdict + glass-box record.
- EVIDENCE MODEL: set evidence_class="race_result" (add it to the impact-gate enum, like diff/callback before
  it), attach artifact_type="state_delta" (the state diff) — SEPARATE field, do NOT merge with evidence_class.

CARRY-FORWARD GUARDRAILS (lessons from Phases 2/3 — do not repeat):
- WIRE THE TOOL: add run_race_harness to _BASE_TOOLS in strix/agents/factory.py AND add a registration test
  asserting it is present in the built agent. (Phase 3 defined tools but never wired them — caught at close-out.)
- THE GATE IS THE FULL SUITE: run `pytest tests/` (whole suite), not per-file — per-file runs hid a real
  report-state bug in Phase 2. Run ruff check . + mypy --strict (changed) + bandit -r strix/ -c pyproject.toml
  together, all green. (Bandit needs -c pyproject.toml or it exits non-zero on pre-existing lows.)
- HERMETIC TESTS: deterministic widened check-then-mutate window for e2e; synthetic tuples for the verdict/
  aggregator PBTs; tempfile/tmp_path for fixtures — NEVER hardcoded /tmp (it broke 3 Phase-3 tests).
- CLEAN WORKING TREE: stage explicit paths, never `git add -A`/`.` — a stray research file got swept into a
  Phase-3 feature commit and had to be scrubbed at merge.
- Credentials: shared-session material redacted in logs, outcome table, and report bodies (inherited from P1).
- Memory/manifest are LOCAL-ONLY: never git-add .agents/ or manifest.yml. Push per task group to
  phase-4-race-harness.
- Update PROGRESS.md / current_focus.md concurrently; set manifest phase-4 status as you progress.
- At close-out, the branch will be SQUASH-merged to main (keeps history clean) — keep the branch tidy.
```
