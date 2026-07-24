# S1 Completion Report — Fail-Closed Scope & Authorization Decision Service

**Date:** 2026-06-18
**Status:** COMPLETE — gate green
**Deliverable:** `strix/core/govern/scope.py` + `tests/test_govern_scope.py`

---

## What Was Built

### `strix/core/govern/scope.py` (new file)

The single deterministic chokepoint for all egress authorization.

**Public API:**
```python
decide(target: Target, ctx: EngagementCtx) -> Decision
load_scope(entries: list[str], *, expires_at=None, action_overrides=None) -> EngagementCtx
```

**Models (Pydantic v2):**
| Model | Fields |
|-------|--------|
| `Target` | `host: str`, `action_class: ActionClass` |
| `EngagementCtx` | `rules: list[ScopeRule]`, `expires_at: datetime | None` |
| `ScopeRule` | `pattern: str`, `allowed_actions: list[ActionClass] | None` |
| `Decision` | `verdict: Verdict`, `reason: str`, `authz_tier: AuthzTier`, `expires_at` |
| `ActionClass` | `recon, port_scan, fingerprint, http, exploit, credential` |
| `Verdict` | `ALLOW, DENY` |
| `AuthzTier` | `standard, high_impact` (exploit/credential classes return HIGH_IMPACT) |

**Decision logic (in `_decide`, wrapped by `decide` for fail-closed error handling):**

1. No rules loaded → `DENY / no_rules` *(fixes the fail-open bug in `_scope.py`)*
2. Context expired → `DENY / expired`
3. First-match rule evaluation:
   - Pattern types: exact hostname, wildcard (`*.foo.com`), exact IP, CIDR
   - If host matches a rule but `allowed_actions` excludes the `action_class` → `DENY / action_class not permitted`
   - If host matches and action is permitted → `ALLOW` with `HIGH_IMPACT` tier for exploit/credential
4. No rule matched → `DENY / out_of_scope`
5. Any exception in `_decide` → outer `decide()` catches and returns `DENY / internal_error: …`

**Relationship to `_scope.py`:** Generalises and supersedes `host_in_scope()`.  The old
function returns `True` when `scope_rules` is empty or `None` (fail-open, the audited bug).
`decide()` returns DENY in that case.  `_scope.py` is left untouched; the S7 integration
step wires `decide()` into the Caido proxy path and replaces `host_in_scope` callsites.

**No LLM in path.** The module imports nothing from `strix.agents`, `strix.tools`, or any
LLM SDK.  It is a pure, synchronous function.

---

## Test Results

**File:** `tests/test_govern_scope.py`

| Group | Tests | Result |
|-------|-------|--------|
| `TestAllowPaths` (TG1.1) | 10 | PASS |
| `TestDenyPaths` (TG1.2) | 8 | PASS |
| `TestErrorPaths` (TG1.3) | 2 | PASS |
| `TestNormalizeHost` | 5 | PASS |
| `TestHostMatches` | 7 | PASS |
| SP1 — `test_sp1_allow_implies_scope_match` | 500 examples | PASS |
| SP2 — `test_sp2_no_rules_always_deny` | 300 examples | PASS |
| SP2 — `test_sp2_expired_always_deny` | 300 examples | PASS |
| SP2 — `test_sp2_no_matching_rule_deny` | 300 examples | PASS |
| **Total** | **36** | **36 PASS** |

**Full gate (406 tests, all existing + new):**
```
406 passed, 4 skipped, 19 subtests passed in 32.72s
```
No regressions. Ruff clean on changed files.

---

## SP1 & SP2 — PBT Verdict

**SP1 (scope soundness):** `decide()` returns `ALLOW` **only** when:
- `ctx.rules` is non-empty
- `ctx.expires_at` is `None` or in the future
- The target host matches at least one rule (by pattern and allowed_actions)

Verified by Hypothesis across 500 generated `(Target, EngagementCtx)` pairs.  Zero
counterexamples.

**SP2 (fail-closed):** Tested across three structural causes:
- Empty rules → `DENY` (300 examples, zero counterexamples)
- Expired context → `DENY` (300 examples, zero counterexamples)
- No matching rule → `DENY` (300 examples, zero counterexamples — cross-checked against
  the structural match predicate to confirm both branches)

---

## Security Readiness (task 1.10)

- No LLM in decision path. ✅
- Not reachable/mutable from agent tools (`strix.tools.*` has no import of this module). ✅
- All error paths return `DENY`. ✅
- No ambient global mutable state in `decide()`. ✅

---

## What Is NOT Done Here (deferred to S7 + later)

- Wiring `decide()` into the Caido HTTP proxy path (`tools/proxy/`) — S7.
- Replacing `host_in_scope()` callsites in inventory collectors — S7.
- Ownership attribution feeding into `decide()` — S2.
- Rate/cred limiter integration — S2.
- Circuit breaker / kill-switch hook — S3.

---

## Handoff to Validator

The decision service is a pure function testable without any infrastructure.
Validation can be reproduced by:
```
cd strix
uv run pytest tests/test_govern_scope.py -v
```
Expected: 36 passed.
