# Phase 1 Kickoff — Locked Contracts + Coder Prompt

> Identity State + Differential (primitives P1 + P2, feature F1). The critical-path gate.
> Source of truth: `.agents/specs/phase-1-identity-differential/{spec.md,tasks.md}` + `manifest.yml`.
> Purpose: lock the two producer interfaces **before** coding, because Phases 3/4/5 consume them.

## Preconditions (verified)
- Phase 0 closed at `0c84009`, branch clean, gates green (ruff / mypy --strict changed-files / 102 tests / bandit). Independently re-verified post-transition.
- Consumes from Phase 0: `pure_url_validator` (`strix/core/net/`), `impact_gate` (`strix/report/state.py`).

---

## Contract A — `identity_store` (P1) · `strix/core/identity/`

Durable, per-target store of authenticated identities. Mirror the `strix/core/sessions.py` `SQLiteSession` persistence pattern; resolve the DB path via `strix/core/paths.py` run dir.

**Identity record (locked fields):**
| Field | Type | Notes |
|---|---|---|
| `target_key` | `str` | canonical per-target key (host[:port] or repo id). **Scoping boundary.** |
| `role` | `str` | label: `anonymous` \| `user` \| `admin` \| custom. De-dup key within a target. |
| `cookies` | `dict[str,str]` | |
| `tokens` | `dict[str,str]` | e.g. `authorization`, `x-api-key` |
| `headers` | `dict[str,str]` | other auth-bearing headers |
| `provenance` | `enum{proxy_capture, login_flow, imported, reserved}` | |
| `freshness` | `{captured_at: iso8601, expires_hint: iso8601\|null, status: enum{fresh,stale,expired}}` | |
| `is_reserved_expired` | `bool` | the auto-seeded `expired` pseudo-identity |

**Invariants (locked — these are the PBT properties):**
- **expired pseudo-identity** auto-seeded per target (`is_reserved_expired=true`, `status=expired`); replay uses deliberately invalid/empty auth; **never treated as authorized** (`∀ s: expired(s) → never authorized`).
- **Uniqueness:** `(target_key, role)` unique; a newer capture for the same role replaces the older.
- **Scoping:** store partitioned by `target_key`; **no API path reads across targets**; `import` rejects a foreign `target_key`.
- **Redaction:** all agent-facing serialization (tool returns, logs, reports) masks `cookies`/`tokens`/`headers` values (`Bearer ****`); credential material is **never** emitted in cleartext anywhere outside the store.

---

## Contract B — `differential_engine` (P2) · `strix/core/diff/`

**Pure, deterministic** (no I/O) → PBT-testable. Two surfaces:

**1. `normalize_response(resp, volatile_patterns) -> NormalizedResponse`**
- Canonicalizes the **locked volatile set**: timestamps, `Date` header, CSRF tokens, nonces, request-ids, `ETag`, session-id values, and `Set-Cookie` *values* (cookie **structure** preserved). Conservative — only declared patterns.
- Records `normalized_fields: list[str]` (glass-box: every normalization is logged).

**2. `diff(responses: list[LabeledResponse], axis) -> DiffResult`**
- `axis ∈ {identity, verb, token, state, header_set}`
- `LabeledResponse = {label: str, response: NormalizedResponse}`

**`SemanticDelta` (per pair — locked output shape):**
| Field | Type |
|---|---|
| `pair` | `(label_a, label_b)` |
| `status_class_delta` | `{a:"2xx", b:"4xx"} \| null` — **bucketed**, not exact code |
| `body_structure_delta` | `enum{same, shape_changed, size_changed}` |
| `normalized_length_delta` | `int` |
| `auth_signal_delta` | `enum{none, gained_access, lost_access}` |
| `set_cookie_delta` | `enum{none, session_set, session_cleared}` |
| `normalized` | `bool` |

**`DiffResult = {deltas: list[SemanticDelta], candidates: list[Candidate]}`**
**`Candidate = {kind: enum{IDOR, BFLA, expired_authorized}, pair, rationale: str, evidence_class: "diff"}`**

**Flagging rules (locked):**
- Identity V (≠ owner U) gets `2xx` where `anonymous`/`expired` gets `4xx` → **IDOR**.
- Low-priv identity shows `gained_access` on an admin-gated function vs the user baseline → **BFLA**.
- `expired` pseudo-identity gets `gained_access`/`2xx` → **expired_authorized**.

**Invariants:** diff-normalization stability (`pair differing only in volatile fields → deltas = ∅`); identity isolation (`∀ a≠b → a recorded delta exists`); **no credential material in any delta/candidate output**.

---

## Supporting interfaces (from the spec, locked)
- **`replay_engine`**: `replay(request_id, identity) -> parsed response` — built on `caido_api.parse_raw_request` → strip original auth → overlay identity creds (`apply_modifications` pattern) → `replay_send_raw` → `parse_raw_response`. **Replay fidelity:** carries exactly the identity's auth, none of the original request's. Must not break/duplicate `repeat_request`.
- **`auth_matrix_tool`** (`@function_tool`): `auth_matrix(request_id) -> {matrix, pairwise_diffs, candidates}` — replays the `anonymous→user→admin→expired` ladder, diffs, flags. Matrix cells **redact** creds.
- **`volatile_field_normalizer`**: the normalizer above, exposed for reuse by the Phase 4 race harness.

---

## Evidence model (resolves the open-question split — do NOT conflate)
- **`evidence_class`** = **strength** taxonomy → drives the Phase 0 impact gate: `diff | callback | reachability | race_result | none`. **Phase 1 always sets `"diff"`** when promoting a candidate; `none` would downgrade to `info`.
- **`artifact_type`** = **media** taxonomy on the evidence *object* (SEPARATE field): `http_exchange | screenshot | file_snippet | shell_output | replay_token`, each with `mime_type` + `ref` (path under the run dir). Renderers switch on `artifact_type`, the gate on `evidence_class`.
- **Wire-up (TG5.3):** when the auth-matrix promotes a candidate, file via `create_vulnerability_report` with `evidence_class="diff"` and attach the `SemanticDelta` + the two `http_exchange` artifacts (creds redacted). Empty diff → no report (impact-gated).

---

## Build order (from tasks.md)
Critical path `TG1 store → TG2 capture → TG3 replay → TG5 tool → TG6 testing`; **TG4 differential develops in parallel against synthetic fixtures**, plugs in at TG5. ~7–8 iterations. Gates: Tier-1 focused tests + the 6 Tier-2 PBT invariants + changed-files `mypy --strict` + ruff + bandit.

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Phase 1 — Identity State + Differential, per .agents/specs/phase-1-identity-differential/
{spec.md,tasks.md} and the locked contracts in this kickoff. Build in critical-path order:
TG1 identity store → TG2 capture/import-export → TG3 replay engine → TG5 tool surface → TG6
testing; build TG4 differential engine in parallel against synthetic response-pair fixtures.

Honor the LOCKED interfaces exactly:
- identity_store record fields and invariants (expired pseudo-identity always present & never
  authorized; (target_key,role) unique; per-target scoping with no cross-target read; credential
  redaction in all agent-facing output).
- differential_engine purity + the SemanticDelta output shape + the volatile-field set; no
  credential material in any delta/candidate.
- evidence model: set evidence_class="diff" on promoted findings (strength, drives the gate);
  put media kind on a SEPARATE artifact_type field. Do NOT merge them.

Guardrails:
- Persist identities via the SQLiteSession pattern (strix/core/sessions.py); paths via core/paths.py.
- Reuse caido_api replay primitives; do not break or duplicate repeat_request.
- Gate before each push: Tier-1 tests + the 6 Tier-2 PBT invariants + `ruff check .` +
  `mypy --strict` on changed files + bandit, all green. Run ruff AND mypy together.
- Memory/manifest are LOCAL-ONLY: never git-add .agents/ or manifest.yml (gitignored by design);
  the pre-commit guard will block it. Write closeout to disk, don't commit it.
- Push to phase-1 work at the end of every task group (push-per-checkpoint), not only at the end.
- Update PROGRESS.md / current_focus.md concurrently as you complete groups.
```
