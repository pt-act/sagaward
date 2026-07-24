# Phase 2 — Native OOB Oracle — Tasks

> Spec-Architect PBT variant · Primitive **P3** · Feature **F2**.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.

---

## Overview

Six task groups build the OOB oracle: the **listener sidecar** (DNS + HTTP(S) capture), **token mint & registry** (per-candidate, unique, per-engagement), the **correlation engine** (attribute hits → candidates), the **agent tool + injection helpers** (F2 inject-and-confirm), **report integration** (impact-gating on a correlated callback), and **testing**. Critical path is `listener → registry → correlation → tool → report`. The **mint/registry + correlation cores develop in parallel** against synthetic mint-log/hit-log fixtures while the sidecar is brought up. Total focused tests: **22** (within 16–34). Target: **~5 iterations**.

---

## Task Group 1 — Listener Sidecar (P3 capture surface)

### Implementation
- [ ] 1.1 OOB listener sidecar in `strix/runtime/oob/`: capture inbound DNS + HTTP(S) on the controlled domain, recording {protocol, token-bearing FQDN/path, source IP, timestamp, raw request} (not_started)
- [ ] 1.2 Bootstrap + readiness probe mirroring `strix/runtime/caido_bootstrap.py`; expose listener ports via `strix/runtime/docker_client.py` / `backends.py` (not_started)
- [ ] 1.3 Per-scan lifecycle mirroring `strix/runtime/session_manager.py` (`create_or_reuse`, port constant, session cache); HTTP(S)-only fallback when DNS delegation is absent (not_started)

### Validation Tier 1: Focused Testing
- [ ] 1.4 Synthetic DNS query to `<token>.<oob-domain>` is captured with token + source recorded (1 test) (not_started)
- [ ] 1.5 Synthetic HTTP(S) request to a token host is captured with token + raw request recorded (1 test) (not_started)
- [ ] 1.6 Readiness probe reports live/down correctly; HTTP-only fallback path captures when DNS is off (1 test) (not_started)

### Security Readiness Checklist
- [ ] 1.7 Listener is self-hosted; no traffic is forwarded to any third-party OOB service (not_started)
- [ ] 1.8 Listener binds only the intended DNS/HTTP ports; no incidental open services (not_started)

---

## Task Group 2 — Token Mint & Registry (P3 core)  *(parallel: develops against fixtures)*

### Implementation
- [ ] 2.1 Token model + unguessable mint; injectable host `<token>.<oob-domain>`; bind to exactly one candidate + originating request ref (not_started)
- [ ] 2.2 Durable per-engagement registry (mint log + hit log) mirroring `strix/core/sessions.py` SQLite pattern; path via `strix/core/paths.py`; per-engagement key, no cross-engagement read path (not_started)
- [ ] 2.3 Live-oracle gate: reject mints while the listener readiness probe is down (not_started)

### Validation Tier 1: Focused Testing
- [ ] 2.4 Mint yields a unique injectable host + a registry row bound to one candidate (1 test) (not_started)
- [ ] 2.5 Mint is rejected when the listener is down; registry survives a restart within an engagement (2 tests) (not_started)

### Validation Tier 2: PBT
- [ ] 2.6 PBT — **token uniqueness / binding**: `∀ t: t unique ∧ bound to exactly one candidate` (not_started)
- [ ] 2.7 PBT — **live-oracle minting**: `∀ minted t: listener_live_at(mint_time(t))` (not_started)

### Security Readiness Checklist
- [ ] 2.8 Tokens are unguessable (sufficient entropy) and minted only by strix (not_started)
- [ ] 2.9 Registry is per-engagement scoped; no cross-engagement read path (not_started)

---

## Task Group 3 — Correlation Engine (P3 core)  *(parallel: develops against fixtures)*

### Implementation
- [ ] 3.1 Extract token from an inbound hit (DNS subdomain label / HTTP host+path); look up in registry; attribute to its single candidate (not_started)
- [ ] 3.2 Quarantine hits whose token was never minted (or belongs to another engagement); never attribute them (not_started)
- [ ] 3.3 Emit structured correlation record {token, candidate, protocol, source, timestamp, latency-from-mint}; record correlation latency (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.4 Minted-token hit attributes to the correct single candidate (1 test) (not_started)
- [ ] 3.5 Unminted / foreign-engagement token hit is quarantined, never attributed (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 3.6 PBT — **correlation correctness**: `∀ hit h: attributed(h) → h.token was minted for that candidate` (not_started)
- [ ] 3.7 PBT — **token unforgeability / scoping**: `∀ hit h of engagement E: attributed(h) → h.token ∈ mints(E)` (not_started)

### Security Readiness Checklist
- [ ] 3.8 Correlation is deterministic over (mint log, hit log); every decision is recorded (glass-box) (not_started)
- [ ] 3.9 No captured hit is silently dropped; quarantined hits are logged, not discarded (not_started)

---

## Task Group 4 — Agent Tool + Injection Helpers (F2)

### Implementation
- [ ] 4.1 `@function_tool` mint + poll/await tools, mirroring `strix/tools/proxy` conventions (`_ctx_client`, `_to_tool_json`, `_err`, JSON returns) (not_started)
- [ ] 4.2 Class-specific injection helpers templating the token host into SSRF / XXE / blind-XSS / async-callback / webhook payloads (agent composes the surrounding request) (not_started)
- [ ] 4.3 F2 inject-and-confirm action: mint → return host → await within window → return correlated result or explicit *unconfirmed* (not_started)

### Validation Tier 1: Focused Testing
- [ ] 4.4 Inject-and-confirm returns a confirmed result (with callback) when a token fires (1 test) (not_started)
- [ ] 4.5 Window expiry with no hit returns explicit *unconfirmed* (never confirmed) (1 test) (not_started)
- [ ] 4.6 Each injection helper embeds the minted host in its class-specific payload shape (1 test) (not_started)

### Security Readiness Checklist
- [ ] 4.7 Tool returns expose the token host only; no other engagement's tokens are listable (not_started)
- [ ] 4.8 An *unconfirmed* result never reads as proof of safety in the tool output (not_started)

---

## Task Group 5 — Report Integration (impact-gating)

### Implementation
- [ ] 5.1 Promote a candidate to a finding only on a correlated callback; attach the callback record (protocol, source, timestamp, token) as PoC via `strix/report/state.py` `add_vulnerability_report` (not_started)
- [ ] 5.2 Suppress confirmation when no correlated callback in window; keep the candidate as unconfirmed (not reported as confirmed) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 5.3 Correlated callback → confirmed `vulnerability_report` carries the callback evidence (1 test) (not_started)
- [ ] 5.4 No callback in window → no confirmed finding promoted (impact-gating) (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 5.5 PBT — **confirmation soundness**: `∀ c: promoted(c) → ∃ correlated callback for c's token` (not_started)
- [ ] 5.6 PBT — **no-false-confirm**: `∀ c: ¬observed(callback(c)) in window → ¬reported_as_confirmed(c)` (not_started)

### Security Readiness Checklist
- [ ] 5.7 Report evidence contains the callback record, never a bare "looks exploitable" assertion (not_started)
- [ ] 5.8 No raw token secrets beyond the captured callback leak into report bodies (not_started)

---

## Task Group 6 — Testing (integration & gap-fill)

### Validation Tier 1: Focused Testing
- [ ] 6.1 End-to-end SSRF: mint → inject token URL into a seeded fetcher → listener captures → correlate → confirmed finding with callback (1 test) (not_started)
- [ ] 6.2 End-to-end blind XXE via DNS: external-entity token host resolved → DNS callback → confirmed (1 test) (not_started)
- [ ] 6.3 Negative end-to-end: injected token never fires within window → candidate stays unconfirmed, no finding (1 test) (not_started)

### Security Readiness Checklist
- [ ] 6.4 Full PBT suite (2.6, 2.7, 3.6, 3.7, 5.5, 5.6) green before audit gate (not_started)
- [ ] 6.5 No target data egresses to any third-party OOB service across the end-to-end path (not_started)

---

> **Focused-test count:** TG1: 3 · TG2: 3 · TG3: 2 · TG4: 3 · TG5: 2 = **13 Tier-1** + **6 Tier-2 PBT** = **19** dedicated; +3 e2e gap-fill (TG6) = **22 total** (within 16–34).

---

## Dependency Mapping & Critical Path

```
TG1 Listener ──────────────────────────┐
                                        ▼
TG2 Mint & Registry (fixtures) ──► TG3 Correlation ──► TG4 Tool + Helpers ──► TG5 Report ──► TG6 Testing
   ▲ parallel with TG1                ▲ parallel with TG1
```

- **TG2** depends on **TG1**'s readiness probe only for the live-oracle gate; its mint/registry core develops against **synthetic fixtures** in parallel with the sidecar.
- **TG3** depends on **TG2** (registry lookup) for attribution; its correlation core also develops against **synthetic mint/hit fixtures**, joining the live listener at integration.
- **TG4** depends on **TG2 + TG3** (mint + correlate behind the agent tool) and on `strix/tools/proxy` conventions.
- **TG5** depends on **TG3 + TG4** (a correlated callback to gate on) and on `report/state.py`.
- **TG6** depends on **all** groups (needs the live listener wired to the correlator).

**Critical path:** `TG1 → TG3 → TG4 → TG5 → TG6` (listener → correlation → tool → report → testing). Mint/registry (TG2) and the correlation core overlap TG1 against fixtures.

---

## Parallelization

- **TG2 (Mint & Registry)** and the **TG3 (Correlation) core** develop in parallel with **TG1 (Listener Sidecar)** against synthetic mint-log/hit-log fixtures, then plug into the live listener at integration. With two developers this removes the registry/correlation cores from the critical path and saves roughly one iteration.
- **Dev A:** TG1 → TG4 → TG5. **Dev B:** TG2 + TG3 (fixtures) then joins TG4/TG6.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Listener Sidecar | 1.5 |
| TG2 Token Mint & Registry | 1 (parallel) |
| TG3 Correlation Engine | 1 (parallel) |
| TG4 Agent Tool + Injection Helpers | 1 |
| TG5 Report Integration | 0.5 |
| TG6 Testing | 1 |
| **Total (sequential)** | **~6 iterations** |
| **With TG2/TG3 parallelized** | **~5 iterations** |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 focused tests pass.
- [ ] **Gate 3** — all Tier-2 PBT invariants validated (token uniqueness/binding, live-oracle minting, correlation correctness, token unforgeability/scoping, confirmation soundness, no-false-confirm).
- [ ] **Gate 4** — security audit on the pre-validated system (impact-gating + self-hosted-listener + no-third-party-egress evidence attached).
