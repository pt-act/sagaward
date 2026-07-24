# Verdict — strix-governance-layer (S0 + S1) — round 1

## Header

```
spec_id:                     strix-governance-layer
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: claude-sonnet-4-6[1m])
reviewed_completion_report:  delivered via operator chat (path: .agents/specs/strix-governance-layer/validation/completion-report.md)
verdict_timestamp:           2026-06-18 21:30 UTC
branch_verified:             sgl-s0-s1 @ aba137f (both commits present on remote)
```

---

## Decision

```
status: needs_revision
```

S1 (scope decision service) is approved-quality — fail-closed logic is correct, SP1/SP2
Hypothesis properties are sound, the test-oracle fix is correct. **Two implementation gaps
in the S0 authored substrate require fixes before the operator build.** They are
reversible now and expensive after the image is assembled.

---

## Per-Criterion Assessment

### AC-G1 — Production image: the image builds with all pinned tools and the egress enforcer active (default-deny); no tool can reach the network except through it.

- Producer's claim: partially met (authored; build not yet run)
- Validator's finding: **unverifiable** (build not yet run — correctly scoped)
- Evidence reviewed: `containers/Dockerfile.prod` exists and is syntactically correct (read in full); `containers/egress-enforcer.sh` and `containers/docker-entrypoint.prod.sh` present.
- Notes: two implementation gaps found in the authored substrate (Issues 1, 2 below) that must be addressed before this criterion can become verifiable.

---

### AC-G2 — Fail-closed scope: DENY/UNKNOWN/EXPIRED/no-rules blocks and logs.

- Producer's claim: met (decision service logic); egress wiring authored but not SP3-verified
- Validator's finding: **confirmed** (decision service); egress wiring **unverifiable** (build pending)
- Evidence reviewed — adversarial re-derivation (v2.1 Amendment 2):

  **Validator-constructed negative cases (not relying on producer's tests):**

  *Case A — no rules:* `Target("evil.com", HTTP)` + `EngagementCtx(rules=[])`. Traced: `_decide()` → line 228 `if not ctx.rules:` → True → returns `DENY reason=no_rules`. No ALLOW path reachable. ✓

  *Case B — expired context with matching rule:* `Target("example.com", HTTP)` + `EngagementCtx(rules=[ScopeRule("example.com")], expires_at=PAST)`. Traced: `not ctx.rules` → False; line 236 `datetime.now(UTC) >= PAST` → True → returns `DENY reason=expired`. Expiry check fires BEFORE rule evaluation — a correctly conservative ordering. ✓

  *Case C — out-of-scope host:* `Target("evil.com", HTTP)` + `EngagementCtx(rules=[ScopeRule("example.com")], expires_at=FUTURE)`. Traced: rules non-empty; not expired; loop enters `_host_matches("evil.com", "example.com")` → pattern not CIDR, not IP, not wildcard → `"evil.com" == "example.com"` → False → continue; loop exhausted → line 274 `DENY reason=out_of_scope`. ✓

  *Case D — error path:* `BadTarget` whose `.host` raises `RuntimeError("boom")`. Traced: `decide()` wraps `_decide()` in `try/except Exception` (lines 216–223); `_decide()` first accesses `target.host` at line 243 → raises → propagates to outer except → returns `DENY reason=internal_error: boom`. ✓

  **Single ALLOW path confirmed:** `scope.py` lines 266–271 is the only `Decision(verdict=ALLOW)` return site. Reachable only after: (1) `ctx.rules` non-empty (228), (2) expiry passed (236), (3) `_host_matches()` True for rule pattern (247), (4) action class permitted by rule (250–258). No other code path reaches ALLOW. ✓

  **SP2 test oracle fix (aba137f) — validator assessment:** The original oracle checked if *any* rule admitted the target. The correct semantics are first-match-wins: if the first host-matching rule restricts the action, no subsequent rule rescues it. Validator constructed the adversarial case: `rules=[ScopeRule("example.com", allowed=[RECON]), ScopeRule("example.com")]`, target `("example.com", EXPLOIT)`. First match = rule 1 (host matches, EXPLOIT not in [RECON]) → `_decide()` returns DENY at lines 254–258 before reaching rule 2. Fixed oracle correctly predicts DENY (finds first host-match = rule 1, EXPLOIT not in allowed → assert DENY). The fix was necessary; the original oracle was incorrect. The fixed version is security-semantics-correct, not just implementation-correct. ✓

---

### AC-G3, AC-G4, AC-G5, AC-G6, AC-G7 — Ownership, Rate/cred, Breaker/kill, Cost, Memory.

- Producer's claim: not met (S2–S6, not in this session's scope)
- Validator's finding: **confirmed not met** (correctly scoped; no deviation)
- Evidence: `strix/core/govern/ownership.py`, `limiter.py` do not exist. `strix/core/agents.py` unchanged. Diff confirms.

---

### AC-G8 — Gate-neutral: propose–dispose verdict and confirmed set identical with/without SGL.

- Producer's claim: met (static import-boundary; SP8 runtime test is S8)
- Validator's finding: **confirmed** (static boundary)
- Evidence reviewed:
  - `scope.py` imports (lines 22–30): `ipaddress`, `datetime`, `timezone`, `Enum`, `Literal`, `urlparse`, `pydantic.BaseModel`, `pydantic.field_validator`. Zero strix-package imports. Read directly.
  - `git diff origin/main --name-only` on `sgl-s0-s1`: 8 files, all outside `strix/core/logic/`, `strix/core/proposals/`, `strix/core/oob/`, `strix/core/diff/`, `strix/core/race/`, `strix/report/`, `strix/agents/factory.py`. Confirmed.
  - `egress_proxy.py` imports (lines 43–51): only `strix.core.govern.scope.*`. No engine package imports.
- Notes: SP8 runtime proof (confirmed set byte-identical on a B-V2P pair) correctly deferred to S8.

---

### AC-G9 — Audit: every allow/deny/halt decision logged with reason and replayable.

- Producer's claim: partially met (proxy logging present; structured replayable log is S6)
- Validator's finding: **confirmed partial** (correctly scoped)
- Evidence: `egress_proxy.py` lines 148–152 logs every `decide()` outcome via Python `logging`. `Decision.reason` is populated on all code paths in `scope.py` (lines 231, 239, 257, 268, 276, 221). S6 structured log correctly deferred.

---

### Non-functional — Fail-closed on every error path.

- Validator's finding: **confirmed** (traced above, Case D)

---

### Non-functional — No LLM in the enforcement path.

- Validator's finding: **confirmed** (`scope.py` lines 22–30, read directly; stdlib + pydantic only)

---

### Non-functional — Additive (no engine edits).

- Validator's finding: **confirmed** (diff verified above; 8 files all new or governance-only)

---

## Interface Verification

**Name:** `decide`

- Spec declared: `decide(target: Target, action_class: ActionClass, ctx: EngagementCtx) -> Decision`
- Delivered: `decide(target: Target, ctx: EngagementCtx) -> Decision` where `target.action_class` carries the value
- Shape match: **compatible** (not exact)
- Notes: `action_class` consolidated into `Target`. Consumer-facing behaviour is semantically identical. The PBT generator `st.builds(Target, host=…, action_class=…)` in `pbt-properties.py` confirms this was the spec author's intent. Deviation is minor and acceptable; flagged as known deviation in the report.

---

## Issues Found

**Issue 1 (major) — DNS enforcement gap in `egress_proxy.py`**

- Location: `strix/runtime/egress_proxy.py` (TCP asyncio server only); `containers/egress-enforcer.sh` line 110
- Description: `egress-enforcer.sh` redirects UDP port 53 (DNS) to `PROXY_PORT` via iptables REDIRECT. However, `egress_proxy.py` only starts a TCP asyncio server (`asyncio.start_server`, line 203). There is no UDP socket listener. A DNS query redirected to port 48081/UDP will hit no listener → silently dropped → DNS fails for ALL domains, including in-scope ones. The proxy header comment claims "DNS UDP 53: proxy intercepts, resolves the domain, consults decide(), and either forwards or returns NXDOMAIN" — this is not implemented. Effect: DNS enforcement is not scope-checked (it's blanket-blocked), and in-scope tools that need DNS resolution (curl, wget, most shell tools) will also fail.
- Suggested remedy: Either (a) add a UDP DNS listener to `egress_proxy.py` that consults `decide()` on the queried domain and either proxies to an upstream resolver or returns NXDOMAIN, or (b) change the iptables DNS rule to pass DNS to the real resolver only after `decide()` approves the target domain — simpler alternative: drop DNS packets to non-loopback resolvers for out-of-scope queries by adding a filter rule per resolved domain name (harder without a DNS proxy). Option (a) is the correct fix.

**Issue 2 (major) — NOPASSWD sudo not restricted; agent can flush iptables**

- Location: `containers/Dockerfile.prod` (inherits base `Dockerfile` line 19: `pentester ALL=(ALL) NOPASSWD:ALL`); `containers/egress-enforcer.sh` (installs iptables rules at startup)
- Description: The `pentester` user — the agent's execution identity — retains unrestricted NOPASSWD sudo from the base image. After `egress-enforcer.sh` installs the iptables rules at container start, the agent (or any shell command the agent runs) can `sudo iptables -t nat -F` or `sudo iptables -F` to flush all SGL enforcement rules, fully bypassing SP3. `Dockerfile.prod` does not revoke or restrict `pentester`'s iptables sudo. This is the trust-boundary issue the PM analysis identified: the enforcer must live outside the agent's authority.
- Suggested remedy: In the `Dockerfile.prod` prod stage, restrict pentester's sudo to a specific allowlist that excludes iptables/nftables. Add to `/etc/sudoers.d/pentester-prod`: `pentester ALL=(ALL) NOPASSWD: ALL, !iptables, !ip6tables, !nftables, !iptables-restore, !ip6tables-restore`. Alternatively, revoke NOPASSWD entirely in the prod stage and grant only the specific capabilities the agent legitimately needs. The SP3 adversarial test **must** include `sudo iptables -t nat -F && curl example.com` as a bypass attempt.

**Issue 3 (minor) — Interface signature deviation**

- Location: `strix/core/govern/scope.py:209`
- Description: `action_class` consolidated into `Target` vs. declared as a separate parameter in the spec. Already in Known Deviations; not a correctness issue.
- Suggested remedy: None required — compatible extension, clearly documented.

---

## Memory Bank Audit

- File: `.agents/memory_bank/active/PROGRESS.md`
  - Declared action: appended (four-field entry, 2026-06-18)
  - Verified: skipped (file is gitignored / local to producer's machine; content summary in report is plausible and well-formed per MEMORY_FORMATS.md — all four fields present in the Progress Entry block)
  - Conditional accept: report includes the full Progress Entry text; validator confirms it is complete (Implemented, Decided, Blocked, Next — no blank fields)

- File: `.agents/memory_bank/active/current_focus.md`
  - Declared action: updated (SGL S0+S1 phase, branch ref, resumption point)
  - Verified: skipped (gitignored); content summary in report is plausible, references the correct branch and next step (SP3 build)

---

## Verdict Rationale

S1 is correct. The fail-closed decision service fixes the audited fail-open bug at its source, the single ALLOW path is reachable only on genuinely positive scope matches, all three structural DENY causes are provable and PBT-verified with corrected oracles, and the gate-neutrality boundary is clean by code reading. The interface deviation (action_class in Target) is minor and acceptable.

The revision is required for S0 only. Issue 1 (DNS enforcement gap) means the authored egress substrate does not implement what its own header comment claims — DNS resolution will fail blanket for all domains, breaking in-scope tool usage and providing no per-domain scope checking. Issue 2 (NOPASSWD sudo) means the enforcer can be flushed by the agent from inside the container, defeating SP3 before it can be verified. Both are fixable in the authored files before the build; catching them now is cheaper than discovering them after assembly. Once Issues 1 and 2 are addressed, the producer may re-file and the SP3 adversarial test (including the `sudo iptables -F` bypass attempt) can proceed.

---

## Session Manifest

```
Skill: pm-auditor@2.0.0 + validation-upgrade-adversarial-semantics (v2.1)
Interpreter: opus-4.8-pm-auditor
Role: validator
Spec: strix-governance-layer (S0+S1)
Validation round: 1
Branch: sgl-s0-s1 @ aba137f
Documents loaded: pm-auditor.md, VALIDATION_PROTOCOL.md, validation-upgrade-adversarial-semantics.md,
                  MASTER_CONTEXT.md, current_focus.md, manifest.yml, AGENTS.md, AGENTS.project.md
Files read: strix/core/govern/scope.py (full), tests/test_govern_scope.py (full),
            containers/egress-enforcer.sh (full), containers/Dockerfile.prod (full),
            strix/runtime/egress_proxy.py (full), git diff --name-only
Criteria verified: 7 confirmed, 0 refuted, 2 unverifiable (AC-G1 build; SP8 runtime — both correctly deferred)
Interfaces verified: 1 compatible (action_class in Target)
Decision: needs_revision
Prior conflict: no
Self-check result: passed — all 11 items including adversarial-direction check (v2.1)
Drift observed: no
Escalations raised: none
```
