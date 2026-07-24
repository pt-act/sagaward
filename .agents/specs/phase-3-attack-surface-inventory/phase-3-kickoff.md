# Phase 3 Kickoff — Locked Contracts + Coder Prompt

> Unified Attack-Surface Inventory (feature F3, reachability seam P4). Feeds Phases 4 and 5.
> Source of truth: `.agents/specs/phase-3-attack-surface-inventory/{spec.md,tasks.md}` + `manifest.yml`.
> Purpose: lock the inventory/classify/spray/reachability contracts before coding; record the FastAPI decision.

## Preconditions (verified)
- Phase 0/1/2 merged to `main` (PRs #3/#4/#5); `main` clean, 31 module files present.
- Consumes: Phase 0 `pinned_toolchain_image` + `scanner_runner` (recon binaries), Phase 1 `differential_engine`. Reachability seeds off the clone path in `strix/interface/utils.py`.
- **Branch from `main`** (it has Phase 0+1): `git checkout -b phase-3-attack-surface-inventory main`.

---

## DECISION (amends spec TG6) — FastAPI is the only required parser this phase

The spec lists five framework parsers (FastAPI, Flask/Django, Express/NestJS, Next.js, GraphQL). Per your preference and the roadmap's "don't parse every framework" guidance, we **narrow Phase 3 to FastAPI only**:
- **FastAPI** is the single **required** reachability parser, tested against a **synthetic FastAPI app fixture** (deterministic, no external repo).
- **Flask/Django, Express/NestJS, Next.js, GraphQL** are **deferred** to a follow-up pass; for now unrecognized stacks **fall through to agent reasoning** (no error).

**Rationale:** FastAPI has the cleanest static introspection (decorated routes + `Depends()` auth), proving the `route→handler→auth-mw→sink` seam fastest; the long tail is explicitly out-of-scope risk. **Black-box `ranked_surface_map` is built regardless** — FastAPI only affects the white-box reachability seam. The six PBT invariants are unchanged.

---

## Contract A — `EndpointObservation` + collectors · `strix/core/inventory/`
Common shape every collector emits (locked): `{method: str, raw_url: str, params: list[ParamObs], source: enum{js, sitemap, ext_tool, code}, raw_evidence: str}`. Exactly **one** source tag per observation.
- Collectors: sitemap (`list_sitemap`/`view_sitemap_entry`), JS routes, external tools (`ffuf`/`katana`/`arjun`/`httpx` — parse output, mirror `web_search._do_search` sanitized-return, run via `tools/shell`), code (white-box, delegates to the FastAPI parser).
- **Scope-bounded** to in-scope hosts via `scope_rules`; never expand surface outside scope. External-tool returns sanitized.

---

## Contract B — `endpoint_normalizer` + dedup · `strix/core/inventory/` *(THE JOIN POINT — the real work)*
- **`normalize(obs) -> (endpoint_key, applied_rules)`** — canonicalize: host-case, default-port strip, trailing-slash, **path-ID templating** (`/users/123 → /users/{id}`), query-key sort. **Conservative** (only declared rules); every applied rule recorded. No over-merge of genuinely distinct endpoints.
- **`dedup(observations) -> map`** — same-key observations merge into one endpoint = **union(sources) ∪ union(params)**.
- **Invariants:** dedup idempotence (`∀ S: dedup(dedup(S)) = dedup(S)`); provenance completeness (`∀ e: sources(e) ≠ ∅`, and a merge carries the union of inputs' sources).

---

## Contract C — scoring + `ranked_surface_map` · `strix/core/inventory/`
- **Signals** (locked set): auth-required, object-ref, state-changing verb, upload, source-multiplicity, reachable-sink. Recorded per endpoint (glass-box, no black-box rank).
- **`score(signals) -> int`** monotonic; **`ranked_surface_map`** = per-target `{endpoint_key → {method+URL, union(sources), union(params), score, provenance}}`, durable via `core/paths.py`.
- **Invariant:** scoring monotonicity (`∀ e₁,e₂ where signals(e₁) ⊋ signals(e₂): score(e₁) ≥ score(e₂)`).

---

## Contract D — param extraction + `parameter_classifier` · `strix/core/inventory/`
- Extract params from proxy traffic (`parse_raw_request`), OpenAPI, JS, HTML forms, (white-box) source; attach to endpoint with provenance + example values; same param from two sources de-dups (unions provenance).
- **`classify(param, evidence) -> class`** — **agent-proposed**, `class ∈ {object-id, url, html, file, amount, role, state}`; records the class **and the evidence used** (a recorded hypothesis, never a verdict).
- **Invariant:** classification determinism (`∀ p with fixed evidence E: classify(p,E)` is stable) — so the downstream spray is reproducible.

---

## Contract E — `class_spray_library` · `strix/core/inventory/` *(deterministic)*
- Fixed spray set per class: `object-id`→IDOR neighbours, `url`→SSRF/OOB targets, `html`→XSS probes, `file`→upload/traversal, `amount`→boundary/negative, `role`/`state`→privilege/transition.
- **`spray(class) -> fixed payload set`** — deterministic, **independent of model output**; emits **candidates only, no execution**.
- **Invariant:** spray determinism (`∀ class c: spray(c)` is a fixed set; only the *choice of class* is agent-proposed — the agent-proposes/harness-disposes boundary holds).

---

## Contract F — FastAPI `reachability_seam` · `strix/core/inventory/` *(white-box / combined only)*
- Detect mode via `infer_target_type` + clone path (`interface/utils.py`); **black-box omits this seam cleanly** (no code collector, no annotation error).
- **FastAPI parser** (read-only over source, no target-code execution): extract `route → handler → auth-middleware (Depends) → sink`. Annotate each endpoint `reachable` (with concrete path) / `unreachable` / `unknown`. Feed `reachable-sink` into the scoring signal set.
- **Invariant:** reachability soundness (`∀ flagged sink k: (∃ path route→handler→k) ∨ marked_unreachable(k)`) — **no unqualified "reachable."**

---

## Candidate boundary (Phase 3 emits candidates, NOT findings)
Phase 3 produces **candidates** (class-spray outputs) and **reachability annotations** — it does **not** file `vulnerability_report`s or set `evidence_class`. Impact-gating stays downstream: when Phase 5 (or F1/F4) files a finding off a reachable sink, *that* is when `evidence_class="reachability"` is set with the concrete path from this seam. Keep the boundary clean.

---

## Build order (from tasks.md)
**TG2 (normalizer+dedup) is the join point and bottleneck** — every leaf converges on it. Critical path `TG1 collectors → TG2 normalize+dedup → TG3 scoring → TG4 classify → TG5 spray → TG8 tools/testing`. **Leaves parallelize:** collectors (TG1), the FastAPI parser (TG6, narrowed), reachability (TG7) develop against fixtures. ~7 iterations. Gate per push: Tier-1 + the **6 PBT invariants** (dedup idempotence, provenance completeness, scoring monotonicity, classification determinism, spray determinism, reachability soundness) + ruff + changed-files `mypy --strict` + bandit.

## Testing — pure cores, offline
Normalizer, dedup, scoring, classify, spray are pure → fixture-test them. FastAPI parser tests run against a **synthetic FastAPI app fixture** (in-repo, no external clone). External-tool collectors parse **captured sample output**, never live tool runs in CI.

---

## Coder kickoff prompt (relay to Hermes)

```text
Ground Phase 3 — Unified Attack-Surface Inventory, per .agents/specs/phase-3-attack-surface-inventory/
{spec.md,tasks.md} and the locked contracts in this kickoff.

START ON A FRESH BRANCH: git checkout -b phase-3-attack-surface-inventory main  (do NOT stack on another
phase branch).

DECISION (amends spec TG6): FastAPI is the ONLY required framework parser this phase, tested against a
synthetic FastAPI app fixture. Flask/Django, Express/NestJS, Next.js, GraphQL are DEFERRED — unrecognized
stacks fall through to agent reasoning, no error. Black-box ranked_surface_map is built regardless.

Build in critical-path order: TG1 collectors → TG2 normalizer+dedup (THE JOIN POINT) → TG3 scoring →
TG4 param extract+classify → TG5 class-spray → TG8 tools+testing; develop the FastAPI parser (TG6) and
reachability seam (TG7) in parallel against fixtures.

Honor the LOCKED interfaces exactly:
- EndpointObservation common shape, one source tag each, scope-bounded (scope_rules), sanitized ext-tool returns.
- endpoint_normalizer: conservative canonicalization with recorded rules; dedup unions sources+params and is
  idempotent; every endpoint keeps ≥1 source (provenance completeness).
- scoring: monotonic over the fixed signal set; signals recorded per endpoint.
- parameter_classifier: agent-proposed class + recorded evidence; deterministic given fixed evidence.
- class_spray_library: deterministic fixed set per class, candidates-only, NO execution, no model output in payloads.
- FastAPI reachability_seam: read-only over source; reachable(path)/unreachable/unknown — never unqualified
  "reachable"; black-box mode omits it cleanly.
- BOUNDARY: Phase 3 emits candidates + reachability annotations only — do NOT file vulnerability_reports or
  set evidence_class; impact-gating is downstream.

Guardrails (lessons from Phase 2):
- THE GATE IS THE FULL SUITE: run `pytest tests/` (whole suite), not per-file — per-file runs hid a real
  report-state bug last phase. Also ruff check . + mypy --strict (changed) + bandit, all green, run together.
- Tests are fixture-driven and offline (synthetic FastAPI app; captured ext-tool output; no live tool runs in CI).
- Persist inventory via core/paths.py; mirror tools/proxy conventions (_ctx_client, _to_tool_json, JSON returns).
- Memory/manifest are LOCAL-ONLY: never git-add .agents/ or manifest.yml. Push per task group to
  phase-3-attack-surface-inventory.
- Update PROGRESS.md / current_focus.md concurrently; set manifest phase-3 status as you progress.
```
