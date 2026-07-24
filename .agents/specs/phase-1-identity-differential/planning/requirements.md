# Phase 1 — Identity State + Differential — Requirements (Planning)

> Spec-Architect PBT variant · Phase 1 of the strix bounty-grade engine.
> Primitives: **P1** (identity/session state) + **P2** (differential engine). Feature **F1** (multi-role authenticated replay + differential).
> This is the **critical-path gate** — nothing downstream reaches its ceiling without it.

---

## Problem / Intent

Strix today repeats requests one-shot (`repeat_request` in `strix/tools/proxy/tools.py`) but has **no durable notion of *who* a request is sent as**. There is no store of authenticated identities, no way to replay one captured request across several roles, and no semantic comparison of the resulting responses. That is precisely the gap that hides the highest-value bug classes: IDOR, broken function-level auth (BFLA), and state-transition bugs are all *differences in behaviour between identities*, and an agent that cannot hold two identities side-by-side cannot see them.

The intent of Phase 1 is to give the agent two composable, deterministic primitives:

- **P1 — Identity / session state:** a durable, per-target store of multiple authenticated identities (role label, cookies, tokens, headers), populated by capturing identities from proxy traffic and from explicit login flows, with session import/export, and the ability to **replay any captured request as any stored identity** — including a built-in **expired/invalid pseudo-identity** for negative testing.
- **P2 — Differential engine:** a response differ that **normalizes volatile fields** (timestamps, CSRF tokens, nonces, request IDs) and reports **semantic deltas** across the axes that matter: identity, verb, token, state, and header-set.

Together they make **F1** a first-class agent action: take any endpoint, replay it across `anonymous → user → admin → expired`, and produce an **auth-matrix with evidence** (a concrete cross-identity diff) rather than a narrative guess.

**Build P1 and P2 as one unit.** Replay without diff is half a feature (roadmap §6 anti-patterns, design note in §2).

---

## Beneficiaries

| Beneficiary | Benefit |
|---|---|
| The strix LLM agent | Gains a deterministic harness it can *compose* (replay-as-identity → diff) instead of hallucinating auth reasoning across raw response dumps. |
| The human bounty operator | Gets auth findings backed by a concrete diff (proof), not scanner spew; attention lands on real IDOR/BFLA. |
| Downstream phases | Phase 4 (race) reuses P1 identities + P2 state-diff; Phase 5 (business-logic) consumes the auth-matrix as substrate; Phase 3 inventory feeds endpoints into F1. |
| The report layer | Receives impact-gated evidence (a diff object) it can attach to a `vulnerability_report` (`strix/report/state.py`). |

---

## Core Functionality

1. **Identity store (P1).** Durable, per-target keyed store of identities. Each identity holds: a role label (e.g. `anonymous`, `user`, `admin`), credential material (cookies, bearer/session tokens, auth headers), provenance (captured vs. imported vs. login-flow), and a freshness marker. A reserved **`expired` pseudo-identity** always exists per target and is never authorized.
2. **Capture.** Derive identities from existing proxy traffic (Caido captures surfaced by `list_requests` / `view_request`) and from explicit login flows (submit credentials, harvest the resulting auth material). De-duplicate so the same role is not stored twice.
3. **Import / export.** Serialize a target's identity set to a portable artifact and reload it, so an engagement's auth state survives container restarts and can be shared across runs.
4. **Replay-as-identity.** Replay any captured request (by request id) *as* any stored identity: strip the original request's auth material and overlay the chosen identity's credentials, then send. Built on the existing replay path (`caido_api.replay_send_raw`, `build_raw_request`).
5. **Differential engine (P2).** Given two (or N) responses, normalize volatile fields and emit a **semantic diff**: status-class change, body structural delta, auth-signal delta (login wall, 401/403, role-gated content), set-cookie delta, length delta beyond normalized noise.
6. **F1 — auth-matrix action.** A single agent tool that, given an endpoint/request, replays across an identity ladder (`anonymous → user → admin → expired`) and returns a matrix of `(identity → response summary)` plus the pairwise semantic diffs and **flagged candidates** (e.g. `user` succeeds on an `admin`-owned resource → IDOR candidate).

---

## User Stories

- **As the strix agent**, I want to store the admin and user sessions I observed in proxy traffic, so that I can replay later requests as either role without re-authenticating.
- **As the strix agent**, I want to replay one captured `GET /api/orders/42` across anonymous/user/admin/expired and get a normalized diff, so that an access-control difference becomes a reportable IDOR/BFLA candidate with evidence.
- **As the strix agent**, I want volatile fields (CSRF tokens, timestamps, nonces) ignored in the diff, so that two genuinely-identical responses do not produce a false delta.
- **As the human operator**, I want to import a session set I captured manually, so that strix tests behind auth I configured by hand.
- **As the human operator**, I want every auth finding to carry the exact cross-identity diff, so that I can verify it in seconds instead of re-running the test myself.
- **As a downstream phase (race/business-logic)**, I want to request "replay this set as identity X with these preconditions", so that I reuse P1/P2 instead of reinventing them.

---

## Constraints

- **WHAT, not HOW** in `spec.md`; no code bodies (program convention).
- **Estimates in iterations**, never time.
- **Impact-gating is non-negotiable:** F1 output is reportable only with a concrete P2 diff as evidence.
- **Glass-box:** every replay records which identity/credentials it used and what was normalized; the diff is inspectable, never a black-box verdict.
- **Credential safety:** stored credential material is secret. It must be redacted in logs/agent-visible summaries, scoped to its owning target, and never leaked across targets or into report bodies.
- **Determinism:** the differ and the volatile-field normalizer must be pure/deterministic so they are PBT-testable and reproducible.
- **Backward compatibility:** must not break or duplicate existing `repeat_request`; build the identity-aware replay on top of the same `caido_api` primitives.
- **Component size:** backend modules cohesive/single-responsibility; any TUI surface ≤ 400 lines.
- **Test budget:** 16–34 focused tests total; security-critical components additionally covered by Tier-2 PBT.

---

## Reusable strix code (reuse before build)

| Module | What it gives us | Use in Phase 1 |
|---|---|---|
| `strix/tools/proxy/tools.py` | `list_requests`, `view_request`, `repeat_request`, `list_sitemap` — capture surface + modification overlay (`modifications` dict: url/params/headers/body/cookies) | Identity **capture** source; replay-as-identity reuses the modification-overlay pattern. |
| `strix/tools/proxy/caido_api.py` | `parse_raw_request`, `build_raw_request`, `apply_modifications`, `full_url_from_components`, `replay_send_raw`, `parse_raw_response` | Core of **replay-as-identity**: parse captured raw → swap auth material → rebuild → send → parse response for the differ. |
| `strix/report/state.py` | `ReportState`, `vulnerability_reports`, severity handling | **Impact-gating** sink: attach the P2 diff as finding evidence. |
| `strix/core/{paths,runner,inputs}.py` | run orchestration + path helpers | Per-target identity-store location (durable path) and run wiring. |
| `strix/core/sessions.py` | `open_agent_session`, `SQLiteSession` pattern (durable per-id SQLite store) | Pattern to mirror for the durable per-target identity store (keyed, file-backed). |
| `strix/tools/{notes,todo,thinking,finish,reporting}/` | existing agent tool-surface conventions (`@function_tool`, JSON string returns, `_ctx_client` context access) | Shape of the new `replay`/`diff`/auth-matrix tools so they plug in identically. |
| `tests/test_core_paths.py` | unittest + spec-loaded-module regression pattern | Mirror for Tier-1 tests. |

---

## Risks / Assumptions

**Assumptions**
- Caido proxy is the capture substrate and is available in the run context (`_ctx_client`); captured requests carry their raw bytes (already true for `view_request`).
- Roles are operator/agent-labelled; **automated credential discovery is out of scope** — strix replays identities it was given or observed, it does not crack/enumerate them.
- "Volatile fields" are enumerable per target via a normalizer ruleset the agent/operator can extend (CSRF/nonce/timestamp/request-id patterns); perfect a-priori knowledge is not assumed.

**Risks**
- **False IDOR positives** from un-normalized volatile fields → mitigated by P2 normalization + the *diff-normalization-stability* invariant (PBT).
- **Credential leakage** across targets or into reports → mitigated by per-target scoping + redaction invariant.
- **Expired-identity drift** (an "expired" session that is actually still valid server-side) → the `expired` pseudo-identity is defined by *intent*; the *expired-session-safety* invariant asserts strix never treats it as authorized, and a still-valid "expired" session is itself a reportable finding, not a contradiction.
- **Login-flow brittleness** (multi-step / captcha logins) → **captcha-solving is out of scope**; login capture targets standard credential POST flows, otherwise falls back to operator import.
- **Over-aggressive normalization** hiding a real delta → normalizer is conservative (only strips fields matching declared volatile patterns) and every normalization is recorded (glass-box).
