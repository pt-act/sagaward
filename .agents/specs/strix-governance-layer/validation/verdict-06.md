# Verdict — strix-governance-layer (SGL-Core) — round 2

## Header
```
spec_id:                     strix-governance-layer (SGL-Core)
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: mimo/mimo-v2.5-pro)
reviewed:                    round-2 summary + branch sgl-s2-s8 @ 773fe56 (feat commit 934732b)
prior_verdict:               verdict-05.md (needs_revision — integration absent)
verdict_timestamp:           2026-06-21 03:30 UTC
```

## Decision
```
status: needs_revision
```

Integration genuinely landed this round — `core/agents.py`, `execution.py`, `runner.py`,
`hooks.py`, `tools/proxy/tools.py` are all modified (+166 lines), and I verified the wiring
in the diff. **Cost ceiling (Blocker 2) is fully and correctly resolved.** But two holes
remain that violate zero-tolerance invariants, and the SP8 test is still near-tautological.

---

## Per-blocker verification

### Blocker 2 (S4a cost ceiling) — RESOLVED ✅
- `execution.py:293-303, 292-303` (both loops): `cost_ceiling.check()` at loop top; `HALT` →
  `kill_switch("cost_ceiling_halt")` → `return result`. The top-of-loop placement means the
  loop genuinely stops. `hooks.py:55-69`: `on_llm_end` records `total_tokens` + `record_tool_call()`.
  Correct. SP7 holds in the wired path.

### Blocker 1 (S3 breaker/kill-switch) — PARTIALLY resolved → **still blocking (SP6)**
- Resolved half: `agents.py:74-90` `kill_switch()` sets `is_shutting_down=True` and
  `await cancel_descendants(root_id)`; `cancel_descendants` (`agents.py:224-232`) calls
  `task.cancel()` on each descendant → **children and their async OOB tasks are halted** (no
  child outlives the kill). Good.
- **Blocking gap:** the breaker trip does **not** halt the *root* agent loop. On `BreakerState.OPEN`
  (`execution.py:443-456`) `_run_cycle` calls `kill_switch` and `return stream` — but neither
  run loop checks `is_shutting_down` at the top. Both loops check **only `cost_ceiling`**
  (`execution.py:96-104` and `:292-303`); the sole `is_shutting_down` reference is `:397`, inside
  the exception handler. After a breaker trip the root's status is still `"running"`
  (`_settle_run_result` is skipped), so `_run_noninteractive_until_lifecycle` re-enters and runs
  **full cycles up to `max_turns`**, each doing real LLM+tool work against the degraded target.
  SP6 (zero-tolerance) says *"no action may complete after a kill"* — the root completes many.
- **Fix:** add `if coordinator.is_shutting_down: return result` at the top of **both**
  `run_agent_loop` (interactive `while True`) and `_run_noninteractive_until_lifecycle`, so the
  flag `kill_switch` already sets actually stops the root. One check per loop.

### Blocker 4 (S7.2 Caido decide()) — WIRED but **fail-open on empty scope → still blocking (SP2)**
- `tools/proxy/tools.py:381-420`: `repeat_request` extracts the replay host and calls `decide()`
  with the engagement scope — correct for the non-empty case, and `runner.py:227-233` now really
  extracts `scope_rules` (was a no-op). Good.
- **Blocking gap:** the guard is `if isinstance(scope_rules_raw, list) and scope_rules_raw:` —
  i.e. it only checks when scope is **non-empty**. With empty/missing scope the `decide()` call
  is **skipped and the replay proceeds**. And Caido runs as **root (uid 0), which the egress
  enforcer exempts** (`--uid-owner 0 -j RETURN`) — the producer's own comment says the app-layer
  `decide()` "is the only layer that catches out-of-scope replays." So an **empty-scope engagement
  lets the agent replay anywhere via Caido**, escaping *both* layers. That is fail-**open** on the
  privileged path, contradicting SP2 (no rules ⇒ DENY) which the egress enforcer honors elsewhere.
- **Fix:** when governance is active (`STRIX_EGRESS_ENFORCE=1`), call `decide()` **regardless of
  whether rules are empty** — `decide()` already returns DENY on empty rules, so the path becomes
  fail-closed. Gate on enforcement-active, not on rules-non-empty.

### Blocker 3 (SP8 genuine test) — **not genuinely fixed → major**
- `test_gate_neutrality.py` was restructured and renamed `test_idor_with_and_without_sgl_gate`
  with a docstring claiming "the genuine gate-neutrality comparison." But the code still: runs
  `_idor.update_memory(...)` with no SGL, calls `decide()` **standalone** (asserts ALLOW), then
  runs the **identical** `_idor.update_memory(...)` again and asserts the two are equal. The
  `decide()` result does not gate/route the disposer — the disposer runs unconditionally after the
  assert. It is the same pure-function-equals-itself comparison as round 1, with better names.
- The *structural* neutrality IS established and I credit it: import-boundary test (SGL imports
  nothing from `core/logic|proposals|oob|diff|race`), `decide()` returns only ALLOW/DENY, and the
  disposer files are untouched. So the property holds — but the dynamic test does not prove it and
  its docstring overclaims that it does.
- **Fix:** either (a) now that SGL is wired into the pipeline, add a real full-pipeline B-V2P
  comparison — run the engine with SGL active vs bypassed and assert the confirmed-finding set is
  byte-identical for allowed actions — or (b) correct the docstring to rest on the structural
  argument and stop claiming a dynamic proof. Do not ship a test whose docstring overclaims.

---

## Issues Found
1. **blocker (SP6) — breaker trip does not halt the root loop.** `execution.py` loops check only `cost_ceiling`; add an `is_shutting_down` check at the top of both loops.
2. **blocker (SP2) — Caido `repeat_request` decide() is fail-open on empty scope** on the root-exempt path. Call `decide()` whenever enforcement is active, not only when rules are non-empty.
3. **major — SP8 test still near-tautological + docstring overclaims.** Add a real full-pipeline with/without-SGL comparison or correct the claim.
4. **minor — breaker records cycle-level latency/errors**, a coarse proxy for target health (the spec framed it per-request). Acceptable first cut; note for later.
5. **minor — completion report** must be re-corrected to reflect these findings; do not re-assert "HOLD LINE reached / E1–E4 may proceed."

## Credit (genuine progress)
- Cost ceiling end-to-end correct (loop-top HALT → kill_switch → return; tokens via hooks).
- kill_switch cancels descendants → children + async OOB tasks halted (no child outlives).
- Caido `decide()` routing + `scope_rules` extraction landed (correct for non-empty scope).
- The integration that was entirely absent in round 1 is now real. This is the right trajectory.

## Verdict Rationale
The producer did the integration this round — the modules are now called from the engine, and
the cost-ceiling halt is correct. Two fail-modes remain, both on the privileged/zero-tolerance
edges: a breaker trip cancels children but lets the root keep completing actions (SP6), and the
Caido replay gate — the one layer that covers root-exempt traffic — is fail-open when scope is
empty (SP2). Both are small, well-localized fixes (one loop check; one guard condition). SP8's
dynamic test remains near-tautological and overclaims, though structural neutrality holds.
needs_revision; HOLD LINE not reached; E1–E4 do not start. These three are Opus-appropriate.

## Session Manifest
```
Skill: pm-auditor@2.0.0 + v2.1 adversarial semantics · validator: opus-4.8-pm-auditor
Spec: strix-governance-layer (SGL-Core) · Round: 2 · Branch: sgl-s2-s8 @ 773fe56 (feat 934732b)
Files read: full diff of agents.py/execution.py/runner.py/hooks.py/tools/proxy/tools.py;
            execution.py loops (90-108, 289-363); is_shutting_down + cancel_descendants greps;
            test_gate_neutrality.py round-2 diff
Decision: needs_revision — 2 blocker (SP6 root-halt, SP2 Caido empty-scope), 1 major (SP8), 2 minor
Zero-tolerance status: SP6 + SP2 violated on edges → blocking; SP8 structurally OK but test weak
Self-check: passed incl. v2.1 adversarial-direction check · Drift: no
```
