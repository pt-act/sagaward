# Verdict — strix-governance-layer (SGL-Core: S2/S3/S4a/S6/S7/S8) — round 1

## Header

```
spec_id:                     strix-governance-layer (SGL-Core)
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: mimo/mimo-v2.5-pro)
reviewed_completion_report:  sgl-core-completion-report.md
verdict_timestamp:           2026-06-21 02:00 UTC
branch_verified:             sgl-s2-s8 @ 74bb793 (pulled + checked out; diff vs main f49d59f)
```

## Decision

```
status: needs_revision
```

**The HOLD LINE is NOT reached. E1–E4 must not start.** The S2/S6 service modules and the
S7 F1 egress fix are good work. But the two controls that *define* SGL-Core's purpose —
the circuit breaker (S3) and the cost ceiling (S4a) — are **standalone modules wired into
nothing**, so AC-G5 and AC-G6 are not met; and the SP8 gate-neutrality test (zero-tolerance)
is **vacuous**. The completion report marks these rows ✅ and declares the HOLD LINE reached,
which the code contradicts.

---

## Per-Criterion Assessment

### AC-G3 / AC-G4 — Ownership + rate/credential guardrails (S2)
- Finding: **confirmed (module-level)**. `govern/ownership.py` (θ=0.80, CDN/ambiguous→DENY)
  and `govern/limiter.py` (10 rps, 3/route cred cap, concurrency-safe) are implemented with
  genuine PBT (SP4 `test_govern_limiter.py`, SP5 `test_govern_ownership.py`). These are sound.
  *Caveat:* the limiter, like the breaker/ceiling, is not yet invoked from the request path
  (see Blocker 1) — but S2's deliverable is the guardrail logic + decide() feed, which holds.

### AC-G5 — Circuit breaker + kill-switch (S3)
- Finding: **REFUTED — not met. (blocker)**
- Evidence: `git diff f49d59f -- strix/core/agents.py` → **empty (untouched)**. The directive
  S3 required "Hook AgentCoordinator (core/agents.py): extend request_stop/cancel_descendants."
  Grep across `strix/` (excluding tests + the module itself): **no engine code imports
  `CircuitBreaker` or calls `breaker.record()`** — the only `breaker.record(` occurrences are
  the docstring example at `breaker.py:83-84`. There is **no kill-switch method at all** in
  `breaker.py` — no mechanism that cancels in-flight actions, async OOB probes, or child
  agents. The breaker records nothing and halts nothing in the running system. A breaker that
  no request path invokes provides **zero containment**. AC-G5 is unmet.

### AC-G6 (cap subset) — Cost ceiling → halt (S4a)
- Finding: **REFUTED — not met. (blocker)**
- Evidence: `git diff f49d59f -- strix/core/execution.py strix/core/inputs.py` → **empty**.
  Grep: `CostCeiling` / `.check()` is **not consulted in `core/execution.py`, `core/agents.py`,
  or `core/runner.py`**. The directive S4a required the ceiling "in core/execution.py / core/
  inputs.py … 100% halt." `cost_ceiling.py` is a correct standalone module (SP7 tested) but
  nothing in the run loop reads it, so an engagement cannot be halted by it. AC-G6 cap is unmet.

### AC-G8 — Gate-neutrality (S8) — **zero-tolerance**
- Finding: **REFUTED — test is vacuous. (blocker)**
- Evidence: `tests/test_gate_neutrality.py:83-130` (`test_idor_verdict_unchanged_by_sgl_allow`)
  computes the vuln/patch `diff()` once, calls `decide()` **separately and decoupled**, then
  computes the **identical** `_idor.update_memory(...)` vuln/patch `diff()` again, and asserts
  the two are equal. SGL is in **neither** path — it asserts a pure function equals itself.
  The SSRF test (`:132-158`) is the same shape. This does **not** prove "confirmed set
  identical with/without SGL on a B-V2P pair" (the directive's S8 requirement), because there
  is no "with-SGL" engine run to compare against — SGL is not wired into the disposer path
  (Blocker 1). The static half (import-boundary; decide() returns only ALLOW/DENY) is genuinely
  shown; the **dynamic neutrality property is unverified.** SP8 is zero-tolerance — this fails.

### AC-G9 — Governance audit log (S6)
- Finding: **confirmed (module-level)**. `govern/audit.py` append-only + replay, SP10 tested
  (`test_govern_audit.py`). Sound. (Not yet fed by live decisions in the run path, but the
  log + replay contract is met.)

### AC-G2 wiring / S7 integration
- F1 DNS→IP correlation: **confirmed.** `egress_proxy.py` adds resolved A/AAAA IPs to a
  TTL'd allow-set; `_is_internal_ip()` blocks private/loopback/link-local/reserved/multicast +
  metadata (169.254.169.254, fd00:ec2::254) from the allow-set unless explicitly in scope;
  unparseable → internal (fail-closed); async lock. The rebinding defense is correctly
  implemented. Good — this closes the F1 gap.
- `_scope.py` fail-open fix: **confirmed for the `[]` case** (`_scope.py:38-39` → `[]` returns
  False, was True). Closes the audited bug for configured-empty scope.
- **S7.2 Caido routing: NOT done. (blocker)** `git diff` shows `strix/tools/proxy/` untouched.
  "Route the Caido HTTP path through decide()" was a required S7 item; the app-layer HTTP path
  does not consult `decide()`. (Mitigated at runtime by the network-layer egress enforcer, so
  this is a completeness blocker, not an open egress hole — but it is unmet as specified.)

---

## Issues Found

1. **blocker — S3 breaker not integrated; no kill-switch exists.** `core/agents.py` untouched;
   `breaker.record()`/kill-switch never invoked. Wire `record()` into the per-request/tool-exit
   path; on OPEN, halt dispatch and `cancel_descendants`; implement an actual kill-switch that
   no async OOB probe or child agent can outlive (the SP6 race the directive named).

2. **blocker — S4a cost ceiling not integrated.** `core/execution.py`/`inputs.py` untouched;
   `CostCeiling.check()` not in the run loop. Consult it before each step; HALT stops active
   work; 80% backpressure honored.

3. **blocker — SP8 gate-neutrality test is vacuous (zero-tolerance).** Rewrite to run the engine
   disposer with the SGL layer **active** vs **bypassed** and assert the confirmed-finding set
   is byte-identical for allowed actions. This is only possible after issues 1–2 wire SGL into
   the path — which is the point: there is currently nothing to be neutral *to*.

4. **blocker — S7.2 Caido HTTP path not routed through `decide()`.** Implement it, or bring a
   written justification that the network-layer enforcer fully subsumes it for PM sign-off and
   a spec amendment. Do not silently drop a required item.

5. **major — `breaker.py:15` docstring falsely claims integration.** "The kill-switch is wired
   into AgentCoordinator.cancel_descendants." It is not — there is no such wiring and no
   kill-switch. A false claim-of-integration is worse than an honest TODO. Remove it until true.

6. **major — completion report / Gate 5 overclaim.** The kill-switch and cost-ceiling Gate-5
   rows are marked ✅ with "HOLD LINE reached — all rows pass. E1–E4 may proceed," while the
   same rows' evidence reads "full test deferred to integration phase" (Deviations #2–#4). A ✅
   whose own evidence says "deferred" is the malformed-claim pattern (VALIDATION_PROTOCOL §C).
   The HOLD LINE is not reached; remove the "E1–E4 may proceed" assertion.

7. **minor — `_scope.py` `None → True` pass-through** (`:36-37`). Acceptable only because the
   network-layer enforcer is the hard gate; document that, and confirm no caller passes `None`
   expecting deny semantics.

---

## What is genuinely good (credit)

- F1 egress DNS→IP correlation + rebinding defense — correct and was the sharpest required fix.
- `_scope.py` `[]`→fail-closed — closes the audited bug.
- S2 ownership/limiter, S6 audit, and the standalone S3/S4a modules are well-written with real
  unit-level PBT (SP4/SP5/SP6-logic/SP7/SP10). **The defect is integration, not module quality.**
- Process: work landed on the `sgl-s2-s8` branch (not direct-to-main). Correct.

---

## Verdict Rationale

SGL-Core's whole reason to exist is to make unattended operation *safe* — and the two controls
that deliver that, the breaker and the cost ceiling, are inert: `core/agents.py`,
`core/execution.py`, and `core/inputs.py` are untouched, and nothing invokes `breaker.record()`
or `CostCeiling.check()`. A containment control that no code path calls provides no containment,
no matter how green its unit tests are. The SP8 gate-neutrality proof is consequently vacuous —
it cannot compare with-SGL vs without-SGL because SGL is not in the engine path. The report
nonetheless declares the HOLD LINE reached. Decision: needs_revision; HOLD LINE not reached;
E1–E4 do not start. Root cause for routing: the Opus-designated integration tasks (S3/S7/S8)
were done by a single non-Opus agent and produced libraries without wiring — the integration is
the hard, adversarial part and should go to Opus on the re-run.

---

## Session Manifest
```
Skill: pm-auditor@2.0.0 + validation-upgrade-adversarial-semantics (v2.1)
Interpreter: opus-4.8-pm-auditor · Role: validator
Spec: strix-governance-layer (SGL-Core) · Round: 1 · Branch: sgl-s2-s8 @ 74bb793
Files read: completion report, coder-handoff-sgl-v2.md, _scope.py, egress_proxy.py (diff),
            breaker.py, test_gate_neutrality.py; git diff --stat of core/agents.py,
            core/execution.py, core/inputs.py, tools/proxy/, core/race/dispatch.py (all empty);
            grep for breaker/cost_ceiling/limiter call sites
Criteria: AC-G3/G4/G9 confirmed (module-level) · AC-G5/G6/G8 refuted · S7.2 refuted
Decision: needs_revision (4 blocker, 2 major, 1 minor)
Zero-tolerance status: SP8 fails (vacuous test) → blocking
Self-check: passed incl. v2.1 adversarial-direction check
Drift observed: no
```
