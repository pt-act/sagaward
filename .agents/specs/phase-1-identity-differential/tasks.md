# Phase 1 — Identity State + Differential — Tasks

> Spec-Architect PBT variant · Primitives **P1 + P2** · Feature **F1**.
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.

---

## Overview

Six task groups build the critical-path gate: a per-target **identity store**, **capture & import/export**, an identity-aware **replay engine**, the **differential engine** (with volatile-field normalizer), the **agent tool surface** (F1 auth-matrix), and **testing**. Critical path is `store → capture → replay → diff → tool`. The **differential engine develops in parallel** against synthetic response-pair fixtures while the replay engine is built. Total focused tests: **24** (within 16–34). Target: **~8 iterations**.

---

## Task Group 1 — Identity Store (P1 core)

### Implementation
- [ ] 1.1 Define identity model: role label, cookies, tokens, headers, provenance, freshness (not_started)
- [ ] 1.2 Durable per-target store keyed by target, mirroring `strix/core/sessions.py` SQLite pattern; path via `strix/core/paths.py` (not_started)
- [ ] 1.3 CRUD + role de-duplication; auto-seed reserved `expired` pseudo-identity per target (not_started)
- [ ] 1.4 Per-target credential scoping + redaction helper for agent-visible summaries (not_started)

### Validation Tier 1: Focused Testing
- [ ] 1.5 CRUD + restart-persistence round-trip (1 test) (not_started)
- [ ] 1.6 Same-role write de-dupes; `expired` always present and never authorized (2 tests) (not_started)

### Validation Tier 2: PBT
- [ ] 1.7 PBT — **credential scoping**: creds of target T never visible outside T, never in cleartext summaries (not_started)
- [ ] 1.8 PBT — **expired-session safety**: `∀ s: expired(s) → never authorized` (not_started)

### Security Readiness Checklist
- [ ] 1.9 Credential material redacted in logs and tool returns (not_started)
- [ ] 1.10 Store file is per-target scoped; no cross-target read path (not_started)

---

## Task Group 2 — Capture & Import/Export (P1)

### Implementation
- [ ] 2.1 Capture identity from proxy traffic via `list_requests`/`view_request` (extract auth material, label role) (not_started)
- [ ] 2.2 Capture from explicit login flow (credential POST → harvest post-login auth material) (not_started)
- [ ] 2.3 Export target identity set to portable artifact; import to reload (not_started)

### Validation Tier 1: Focused Testing
- [ ] 2.4 Proxy-capture stores correct labelled, redacted identity (1 test) (not_started)
- [ ] 2.5 Login-flow capture harvests post-login auth material (1 test) (not_started)
- [ ] 2.6 Export → import round-trip yields identical set, creds intact (1 test) (not_started)

### Security Readiness Checklist
- [ ] 2.7 Exported artifact treats creds as secret (no incidental plaintext leak into logs) (not_started)
- [ ] 2.8 Import rejects identities for a foreign target key (not_started)

---

## Task Group 3 — Replay Engine (P1 → F1 substrate)

### Implementation
- [ ] 3.1 Replay-as-identity: parse captured raw (`caido_api.parse_raw_request`), strip original auth, overlay identity creds (extend `apply_modifications` overlay pattern), send via `replay_send_raw` (not_started)
- [ ] 3.2 Parse response (`parse_raw_response`) into the differ's input shape; surface per-identity failures, never drop (not_started)
- [ ] 3.3 Identity-ladder fan-out: replay one request across `anonymous → user → admin → expired` (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.4 Replay-as-identity substitutes the right creds; ladder returns one cell per identity (1 test) (not_started)
- [ ] 3.5 Replay failure surfaces per-identity instead of dropping the cell (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 3.6 PBT — **replay fidelity**: `∀ r,i: replay(r,i)` carries exactly `i`'s auth material and none of `r`'s original auth (not_started)

### Security Readiness Checklist
- [ ] 3.7 No original-request credential survives substitution (not_started)
- [ ] 3.8 Does not break or duplicate existing `repeat_request` path (not_started)

---

## Task Group 4 — Differential Engine (P2)  *(parallel: develops against fixtures)*

### Implementation
- [ ] 4.1 Volatile-field normalizer: strip/canonicalize declared volatile patterns (timestamps, CSRF, nonces, request-ids); record what was normalized (not_started)
- [ ] 4.2 Semantic differ across axes identity/verb/token/state/header-set: status-class, body-structure, auth-signal, set-cookie, normalized-length deltas (not_started)
- [ ] 4.3 Candidate flagging: cross-owner success → IDOR/BFLA candidate; auth-signal collapse → BFLA candidate (not_started)

### Validation Tier 1: Focused Testing
- [ ] 4.4 Status-class + auth-signal delta detected on a fixture pair (1 test) (not_started)
- [ ] 4.5 Cross-owner success flags an IDOR candidate on a fixture (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 4.6 PBT — **diff normalization stability**: pair differing only in volatile fields → semantic diff = ∅ (not_started)
- [ ] 4.7 PBT — **identity isolation**: `∀ a≠b: replay(r,a),replay(r,b)` → a recorded diff exists (not_started)
- [ ] 4.8 PBT — **IDOR detection**: `∀ resource owned by U, V≠U: success as V → flagged` (not_started)

### Security Readiness Checklist
- [ ] 4.9 Normalizer is conservative (only declared patterns) and every normalization is recorded (glass-box) (not_started)
- [ ] 4.10 Diff never emits credential material in its delta output (not_started)

---

## Task Group 5 — Agent Tool Surface (F1)

### Implementation
- [ ] 5.1 `@function_tool` identity-store ops (list/capture/import/export), mirroring `strix/tools/proxy` conventions (`_ctx_client`, JSON returns) (not_started)
- [ ] 5.2 `@function_tool` replay-as-identity + auth-matrix action (replay ladder → matrix + pairwise diffs + candidates) (not_started)
- [ ] 5.3 Impact-gating wire-up: attach non-empty diff as evidence into `strix/report/state.py` `vulnerability_reports`; suppress report when diff empty (not_started)

### Validation Tier 1: Focused Testing
- [ ] 5.4 Auth-matrix tool returns matrix + pairwise diffs + candidates for a seeded endpoint (1 test) (not_started)
- [ ] 5.5 Empty diff → no finding promoted (impact-gating) (1 test) (not_started)

### Security Readiness Checklist
- [ ] 5.6 Tool returns redact credentials in matrix cells (not_started)
- [ ] 5.7 Report evidence contains the diff, never cleartext creds (not_started)

---

## Task Group 6 — Testing (integration & gap-fill)

### Validation Tier 1: Focused Testing
- [ ] 6.1 End-to-end F1: capture → store → replay ladder → diff → auth-matrix on a seeded IDOR test target (1 test) (not_started)
- [ ] 6.2 End-to-end BFLA: low-priv identity reaches admin-gated function → flagged with diff evidence (1 test) (not_started)
- [ ] 6.3 Expired-identity end-to-end: server still authorizes "expired" session → flagged as finding, not dropped (1 test) (not_started)

### Security Readiness Checklist
- [ ] 6.4 Full PBT suite (1.7, 1.8, 3.6, 4.6, 4.7, 4.8) green before audit gate (not_started)
- [ ] 6.5 No credential leakage across the end-to-end path (logs, matrix, report) (not_started)

> **Focused-test count:** TG1: 3 · TG2: 3 · TG3: 2 · TG4: 2 · TG5: 2 · TG6: 3 = **15 Tier-1** + **6 Tier-2 PBT** = **21** dedicated; +3 e2e gap-fill counted above = **24 total** (within 16–34).

---

## Dependency Mapping & Critical Path

```
TG1 Store ──► TG2 Capture ──► TG3 Replay ──┐
                                           ├──► TG5 Tool Surface ──► TG6 Testing
TG4 Differential (fixtures) ───────────────┘
   ▲ parallel with TG2/TG3
```

- **TG2** depends on **TG1** (capture writes to the store).
- **TG3** depends on **TG1** (replay reads identities) and **TG2** (needs captured identities/requests).
- **TG4** depends only on **TG1**'s identity model for axis labels; otherwise develops against **synthetic fixtures** — no dependency on TG3.
- **TG5** depends on **TG3 + TG4** (auth-matrix = replay ladder + diff) and on `report/state.py` for impact-gating.
- **TG6** depends on **all** groups.

**Critical path:** `TG1 → TG2 → TG3 → TG5 → TG6` (store → capture → replay → tool → testing). The diff engine (TG4) is off the critical path.

---

## Parallelization

- **TG4 (Differential Engine)** develops in parallel with **TG2/TG3** against synthetic response-pair fixtures, then plugs in at **TG5**. With two developers this removes TG4 from the schedule and saves roughly one iteration.
- **Dev A:** TG1 → TG2 → TG3 → TG5. **Dev B:** TG4 (fixtures) then joins TG5/TG6.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Identity Store | 1.5 |
| TG2 Capture & Import/Export | 1.5 |
| TG3 Replay Engine | 1.5 |
| TG4 Differential Engine | 1.5 (parallel) |
| TG5 Agent Tool Surface | 1 |
| TG6 Testing | 1 |
| **Total (sequential)** | **~8 iterations** |
| **With TG4 parallelized** | **~7 iterations** |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 focused tests pass.
- [ ] **Gate 3** — all Tier-2 PBT invariants validated (identity isolation, IDOR detection, expired-session safety, diff normalization stability, credential scoping, replay fidelity).
- [ ] **Gate 4** — security audit on the pre-validated system (impact-gating + credential-scoping evidence attached).
