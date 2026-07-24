# Phase 2 Kickoff — Locked Contracts + Coder Prompt

> Native OOB Oracle (primitive P3, feature F2). The truth oracle for blind classes.
> Source of truth: `.agents/specs/phase-2-oob-oracle/{spec.md,tasks.md}` + `manifest.yml`.
> Purpose: lock the provider/registry/correlator interfaces before coding, and record the interactsh decision.

## Preconditions (verified)
- Phase 1 closed/verified; Phase 0 produced the `oob_confirmation_seam` (null impl) this phase replaces.
- **`interactsh-client` is already bundled** (`containers/Dockerfile:108`, `go install …/interactsh-client@latest`).
- **`strix/runtime/caido_bootstrap.py`** is the sidecar bootstrap + readiness-probe pattern to mirror.
- Consumes from Phase 0: `impact_gate` (`strix/report/state.py`), `oob_confirmation_seam`.

---

## DECISION (amends the spec) — OOB backend: interactsh, provider-abstracted

The spec scoped the listener **self-hosted only** and put hosted interactsh *Out of Scope*. **We are relaxing that** to a provider abstraction:

- **Default = public interactsh servers** (ProjectDiscovery: `oast.pro`/`oast.fun`). Full **DNS + HTTP(S) + SMTP** confirmation for **$0, no domain required** — the capability the original "HTTP-only fallback" would have lost. strix already ships the client.
- **Self-hosted `interactsh-server`** remains a **config-only flip** (`oob.server_url`) for when a domain is available — the original spec's vision, preserved as an upgrade path, not the prerequisite.

**Rationale:** full DNS confirmation now at zero cost; strix already bundles `interactsh-client`; self-host stays available for sensitive work.

**Tradeoff to document as a known limitation:**
- Public OAST domains can be WAF-**blocklisted** → false **negatives** on sophisticated targets. This is **fail-safe**: a blocked callback yields "unconfirmed," never a false positive (consistent with the no-false-confirm invariant). It's the reason to flip to self-hosted for those targets.
- With public interactsh, only your **correlation tokens** (and the target's resolver/source IP) transit ProjectDiscovery infra — **no payload or sensitive target data**. For sensitive engagements, self-host.

**All six P3 invariants are unchanged** by this decision — only the backend behind `OobProvider` differs.

---

## Architecture refinement (interactsh vs. a from-scratch DNS server)
The "listener sidecar" (TG1) is **not** a hand-rolled DNS/HTTP server. It is **`interactsh-client` managed as a sidecar** (bootstrap via the `caido_bootstrap.py` pattern), connected to the configured interactsh server, **streaming interactions**. The OAST **base host** comes from the interactsh session; per-candidate tokens are **subdomain labels** prepended to that base. This removes most of TG1's from-scratch listener work — it becomes client bring-up + interaction parsing.

---

## Contract A — `OobProvider` · `strix/runtime/oob/`
Backend abstraction (the swap point):
| Member | Shape | Notes |
|---|---|---|
| `start()` / `ready() -> bool` | — | session established + server reachable; mirrors `caido_bootstrap` readiness |
| `base_host` | `str` | OAST base from the interactsh session, e.g. `c8xj…oast.pro` |
| `poll_interactions() -> Iterable[OobHit]` | stream | parses interactsh-client interaction output |
| `config` | `{provider: "interactsh", server_url: str\|null, token: str\|null}` | `server_url=null` → public default; set → self-hosted |

`InteractshProvider` is the only implementation needed now. **Pin `interactsh-client`** (currently `@latest`) per Phase 0 discipline.

---

## Contract B — token model + `token_registry` · `strix/core/oob/`
**`OobToken`** (locked): `{token: str (unguessable, ≥128-bit), candidate_ref: str, request_ref: str, minted_at: iso8601, window_s: int, injectable_host: str}` where `injectable_host = f"{token}.{provider.base_host}"`.

**`OobHit`** (locked): `{protocol: enum{dns,http,https,smtp}, full_host: str, token: str|null, source_ip: str, timestamp: iso8601, raw: str}`.

**Registry** (durable, per-engagement; mirror `core/sessions.py` SQLite, path via `core/paths.py`):
- `mint(candidate_ref, request_ref) -> OobToken` — **rejects if `provider.ready()` is false** (live-oracle gate).
- mint-log + hit-log; **per-engagement key, no cross-engagement read path**.

**Invariants:** token uniqueness/binding (`∀ t unique ∧ bound to exactly one candidate`); live-oracle minting (`∀ minted t: ready() at mint_time`).

---

## Contract C — `correlator` · `strix/core/oob/`
**Pure/deterministic** over (mint-log, hit-log):
`correlate(hit: OobHit, registry) -> CorrelationRecord | Quarantined`
- extract token from `hit.full_host` (DNS subdomain label / HTTP host) → registry lookup → attribute to its single candidate.
- **`CorrelationRecord`** (locked): `{token, candidate_ref, protocol, source_ip, timestamp, latency_from_mint_s}`.
- unminted / foreign-engagement token → `Quarantined` (logged, **never** attributed, never silently dropped).

**Invariants:** correlation correctness (`∀ attributed h: h.token was minted for that candidate`); token unforgeability/scoping (`∀ hit h of E: attributed(h) → h.token ∈ mints(E)`).

---

## Contract D — F2 tool + injection helpers + report · `strix/tools/oob/`
- `@function_tool` `oob_mint` / `oob_inject_and_confirm(candidate_ref, request_ref, payload_class, window_s)` — mirror `strix/tools/proxy` conventions (`_ctx_client`, `_to_tool_json`, `_err`).
- **Flow:** mint → return `injectable_host` → await/poll within window → return **confirmed (with callback evidence)** or **explicit `unconfirmed`** (never "safe").
- **Injection helpers** (`payload_class ∈ {ssrf, xxe, blind_xss, async_callback, webhook}`) template `injectable_host` into the class-specific payload shape; the agent composes the surrounding request.
- **Report wiring (impact-gating):** on a correlated callback, file via `create_vulnerability_report` with **`evidence_class="callback"`** and attach the `CorrelationRecord` as **`artifact_type="oob_callback"`**. No callback in window → **no confirmed finding**.

---

## Evidence model (extends Phase 1's split — keep consistent)
- **`evidence_class`** (strength, drives the gate): Phase 2 sets **`"callback"`** (the second value after Phase 1's `"diff"`). Enum: `diff | callback | reachability | race_result | none`.
- **`artifact_type`** (media, SEPARATE field): Phase 2 adds **`"oob_callback"`** to the existing `{semantic_delta, http_exchange}`. Renderers switch on `artifact_type`, the gate on `evidence_class`. **Do NOT merge them** — same rule as Phase 1.

---

## Build order (from tasks.md)
Critical path `TG1 interactsh-client sidecar → TG3 correlation → TG4 tool → TG5 report → TG6`; **TG2 mint/registry + TG3 core develop in parallel against synthetic `OobHit`/mint-log fixtures**. ~5 iterations. Gate per push: Tier-1 tests + the **6 PBT invariants** (token uniqueness/binding, live-oracle minting, correlation correctness, token unforgeability/scoping, confirmation soundness, no-false-confirm) + ruff + changed-files `mypy --strict` + bandit.

## Testing — deterministic & offline
The registry and correlator are pure → unit-test them against **synthetic `OobHit`/mint-log fixtures**, never by hitting public `oast.pro` in CI. The interactsh integration is a **thin adapter** kept out of unit tests. For an e2e, run a **local `interactsh-server` + client** and point a controlled fixture target at it — no public infra, no flakiness.

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Phase 2 — Native OOB Oracle, per .agents/specs/phase-2-oob-oracle/{spec.md,tasks.md} and
the locked contracts in this kickoff. DECISION (amends the spec's self-hosted-only stance):
the OOB backend is interactsh behind an OobProvider abstraction — PUBLIC interactsh servers by
default (server_url=null), with self-hosted interactsh-server as a config-only flip. interactsh-client
is already bundled (containers/Dockerfile); pin its version. The sidecar is interactsh-client managed
via the caido_bootstrap.py pattern, NOT a from-scratch DNS server.

Build in critical-path order: TG1 interactsh-client sidecar → TG3 correlation → TG4 tool+helpers →
TG5 report → TG6 e2e; build TG2 mint/registry + the TG3 correlation core in parallel against synthetic
OobHit/mint-log fixtures.

Honor the LOCKED interfaces exactly:
- OobProvider (start/ready/base_host/poll_interactions/config); InteractshProvider only.
- token_registry: unguessable token, injectable_host=<token>.<base_host>, per-engagement scoping with
  no cross-engagement read, and the live-oracle gate (reject mint if provider.ready() is false).
- correlator: pure over (mint-log, hit-log); unminted/foreign-engagement token → Quarantined, never
  attributed, never dropped.
- evidence model: set evidence_class="callback" on confirmed findings (strength, drives the gate),
  and attach the CorrelationRecord as artifact_type="oob_callback" (media, SEPARATE field). Do NOT merge.
- impact-gating: no correlated callback in window → NO confirmed finding; unconfirmed never reads as "safe".

Guardrails:
- Persist registry via the SQLiteSession pattern (core/sessions.py); paths via core/paths.py.
- Mirror strix/tools/proxy tool conventions; mirror caido_bootstrap for sidecar bring-up.
- Unit tests are fixture-driven and offline (no public oast.pro in CI); keep the interactsh adapter thin.
- Document the public-OAST limitation (WAF blocklist → fail-safe false negatives; self-host to mitigate).
- Gate before each push: Tier-1 + all 6 PBT invariants + ruff + mypy --strict (changed) + bandit, green;
  run ruff AND mypy together.
- Memory/manifest are LOCAL-ONLY: never git-add .agents/ or manifest.yml. Push per task group.
- Update PROGRESS.md / current_focus.md concurrently; set manifest phase-2 status as you progress.
```
