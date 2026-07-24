# Phase 3 — Unified Attack-Surface Inventory — Requirements (Planning)

> Spec-Architect PBT variant · Phase 3 of the strix bounty-grade engine.
> Primitive seam: **P4** (reachability map, white-box/combined mode). Feature **F3** (unified endpoint/parameter inventory) — *feeds every later phase*.
> Source: `strix-bounty-roadmap.md` §Phase 3, §5 (P4 cross-cutting), §1 principles. Program index: `specs/README.md`.

---

## Problem / Intent

Strix today discovers attack surface from several disconnected sources — JS route hints, the Caido proxy sitemap (`list_sitemap` in `strix/tools/proxy/tools.py`), and external recon tools the agent can shell out to (`ffuf`/`katana`/`arjun`/`httpx`) — but it has **no single, deduplicated, ranked view of "what is the target's attack surface"**. The agent re-walks the same endpoints, misses parameters that only one source saw, and has no principled way to decide *which* endpoint to attack first. Worse, in white-box/combined mode (a repo in scope) there is no link from a discovered route back to its handler, its auth middleware, and the dangerous sinks it reaches — so the agent treats reachable and unreachable code identically and drowns in noise.

The roadmap is explicit about where the value is: **"the collection is easy; the dedup + scoring into a single map is the real work."** Collecting URLs is a solved problem the moment external tools run; the hard, durable primitive is correlating heterogeneous sources into **one ranked attack-surface map** with deduplicated endpoints, classified parameters, and (white-box) a reachability annotation.

The intent of Phase 3 is to give the agent three composable things:

- **A unified endpoint inventory.** Correlate endpoints from JS-discovered routes, the proxy sitemap, external tools (`ffuf`/`katana`/`arjun`/`httpx`), and code-discovered routes when source is available; **normalize → deduplicate → score** into a single ranked map, where every endpoint records the source(s) that found it (provenance).
- **A parameter-centric layer.** Extract parameters from proxy traffic, OpenAPI specs, JS, HTML forms, and source; let the **agent classify** each parameter by type (`object-id` / `url` / `html` / `file` / `amount` / `role` / `state`); then apply **deterministic, class-specific sprays** per type (this is the agent-proposes / harness-disposes split from §1 principle 2).
- **A P4 reachability seam.** When source is in scope, associate `route → handler → auth-middleware → sink` so the inventory can mark endpoints reachable/unreachable and filter white-box noise before the agent spends effort on it.

**The dedup + scoring is the feature; the collectors are plumbing.** (roadmap §Phase 3, §6 anti-pattern "parsing every framework").

---

## Beneficiaries

| Beneficiary | Benefit |
|---|---|
| The strix LLM agent | Gets one ranked surface map instead of N overlapping source dumps; spends effort on the highest-signal endpoints/params first, and (white-box) skips unreachable code. |
| The human bounty operator | Sees a single inspectable attack-surface map per target with provenance per endpoint and a class per parameter — recon is auditable, not a pile of tool output. |
| Downstream phases | Phase 1 (F1) replays the inventory's ranked endpoints across the identity ladder; Phase 4 (race) draws its candidate request set from classified `amount`/`state` params; Phase 5 (business-logic) consumes the map as its substrate for journey modeling. |
| The report layer | Param-class sprays produce targeted IDOR/SSRF/XSS/mass-assignment candidates that still pass impact-gating (`strix/report/state.py`) downstream — recon feeds evidence, it does not bypass it. |

---

## Core Functionality

1. **Source collectors.** Adapters that normalize each source into a common `EndpointObservation` shape: (a) JS-discovered routes, (b) proxy sitemap (`list_sitemap`/`view_sitemap_entry`), (c) external tools `ffuf`/`katana`/`arjun`/`httpx` (run in-sandbox, output parsed), (d) code-discovered routes when source is in scope. Each observation carries its source tag = provenance.
2. **Normalizer.** Canonicalize method + URL (lowercase host, strip default ports, collapse trailing slash, template path-IDs `/users/123 → /users/{id}`, sort query keys) so observations from different sources become comparable. Normalization is deterministic and recorded.
3. **Deduplicate + score.** Merge observations that normalize to the same endpoint key into one endpoint carrying the **union of sources** and the **union of parameters**; assign a rank score from attack-surface signals (auth-required, object-ref present, state-changing verb, file upload, multiplicity of sources, reachable sink in white-box). Emit **one ranked map** per target.
4. **Parameter extraction.** Pull params from proxy traffic, OpenAPI, JS, HTML forms, and source; attach each to its endpoint with provenance and observed example values.
5. **Parameter classification (agent-proposed).** The agent classifies each param into one of `object-id / url / html / file / amount / role / state` from its evidence (name, location, example values, surrounding context). Classification is a hypothesis, recorded with its evidence.
6. **Class-specific sprays (deterministic).** A fixed library maps each class to a deterministic spray set — `object-id`→IDOR neighbours, `url`→SSRF/OOB callback targets, `html`→XSS probes, `file`→upload/path-traversal payloads, `amount`→boundary/negative/overflow values, `role`/`state`→privilege/transition values. The **classification is agent-proposed; the spray for a given class is deterministic** (no model output in the payload set).
7. **Framework-aware route parsers (top stacks only).** Code-route extraction for FastAPI, Flask/Django, Express/NestJS, Next.js, GraphQL; the long tail is left to agent reasoning (roadmap §5 advice #9, program-level out-of-scope).
8. **P4 reachability seam (white-box/combined mode).** When a repo is in scope (seeded via the clone path in `strix/interface/utils.py`), build `route → handler → auth-middleware → sink` associations so each endpoint can be annotated reachable / unreachable / unknown, and so a flagged sink always has a concrete reachable path or is marked unreachable.

---

## User Stories

- **As the strix agent**, I want one ranked attack-surface map per target, so that I attack the highest-signal endpoints first instead of re-walking overlapping source dumps.
- **As the strix agent**, I want each endpoint to record which sources found it, so that I can trust a high-confidence endpoint and treat a single-source hit with appropriate skepticism.
- **As the strix agent**, I want each parameter classified by type with a deterministic spray for that type, so that an `object-id` param gets IDOR neighbours and a `url` param gets SSRF callbacks without me hand-writing payloads.
- **As the strix agent (white-box)**, I want routes associated with their handler, auth middleware, and reachable sinks, so that I ignore unreachable code and only chase sinks an actual request can hit.
- **As the human operator**, I want the surface map and its scores to be inspectable (provenance + classification evidence shown), so that recon is auditable rather than a black-box ranking.
- **As a downstream phase (race / business-logic)**, I want to draw a candidate request set filtered by param class (`amount`, `state`), so that I reuse F3 instead of re-deriving the surface.

---

## Constraints

- **WHAT, not HOW** in `spec.md`; no code bodies (program convention).
- **Estimates in iterations**, never time.
- **Agent proposes, harness disposes:** parameter **classification** is a model hypothesis; the **spray** for each class is deterministic. The model never both classifies *and* invents the payload set (roadmap §1 principle 2, §6 anti-pattern).
- **Determinism:** normalizer, dedup, scoring, and the spray library are pure/deterministic → reproducible and PBT-testable. Same evidence ⇒ same class-spray ⇒ same candidates.
- **Provenance is mandatory:** every endpoint in the map records ≥1 source; nothing appears without a recorded origin (glass-box).
- **Reachability soundness (white-box):** a flagged sink must have a demonstrated reachable path *or* be explicitly marked unreachable — never an unqualified "reachable."
- **Top stacks only:** framework-aware extraction covers FastAPI, Flask/Django, Express/NestJS, Next.js, GraphQL; the long tail is the agent's job (out of scope here).
- **No exploitation here:** Phase 3 *produces* candidates; it does not execute exploits or promote findings. Impact-gating still happens downstream.
- **Component size:** backend modules cohesive/single-responsibility; any TUI surface ≤ 400 lines.
- **Test budget:** 16–34 focused tests total; dedup/classification/scoring additionally covered by Tier-2 PBT.

---

## Reusable strix code (reuse before build)

| Module | What it gives us | Use in Phase 3 |
|---|---|---|
| `strix/tools/proxy/tools.py` | `list_sitemap`, `view_sitemap_entry`, `list_requests`, `view_request`, `scope_rules`, `_ctx_client` / `_to_tool_json` tool conventions | **Sitemap collector** + **proxy-traffic parameter source**; scope rules bound the inventory to in-scope hosts. |
| `strix/tools/proxy/caido_api.py` | `list_sitemap_with_client`, `_clean_sitemap_metadata`/`_clean_sitemap_request_summary` (sitemap node shape), `parse_raw_request`, `parse_raw_response`, `full_url_from_components` | Normalize sitemap nodes and raw requests into the common `EndpointObservation`/parameter shape. |
| `strix/interface/utils.py` | `infer_target_type` (web vs repository vs local_code), `clone_repository`/clone path, `RepoDiffScope`, `resolve_diff_scope_context`, localhost→gateway URL rewriting | Decide black-box vs white-box/combined mode; **seed the P4 reachability map** from the clone path; URL normalization anchor for the endpoint normalizer. |
| `strix/tools/web_search/tool.py` | `web_search`, sandboxed `_do_search` with sanitized returns | Pattern for **wrapping an external tool** (sandboxed call → parse → sanitized JSON return) the collectors mirror for `ffuf`/`katana`/`arjun`/`httpx`. |
| `strix/tools/shell/` | shell tool surface for running sandboxed binaries | Run the bundled external recon tools (pinned in Phase 0 toolchain) and capture their output for the collectors. |
| `strix/report/state.py` | `ReportState`, `vulnerability_reports`, severity handling | Downstream sink — sprays produce candidates; impact-gating still applies before reporting (not bypassed by recon). |
| `strix/tools/{notes,todo,thinking,reporting}/` | `@function_tool`, JSON-string returns, `_ctx_client` context access | Shape of the new inventory / classify / spray agent tools so they plug in identically. |
| `strix/core/{paths,runner,inputs}.py` | run orchestration + durable path helpers | Per-target inventory store location and run wiring. |
| `tests/test_core_paths.py` | unittest + spec-loaded-module regression pattern | Mirror for Tier-1 tests. |

---

## Risks / Assumptions

**Assumptions**
- The external recon tools (`ffuf`/`katana`/`arjun`/`httpx`) are bundled and runnable in-sandbox (Phase 0 toolchain exit criterion); collectors parse their output, they do not vendor the tools.
- Caido proxy traffic + sitemap are available via `_ctx_client` (already true for `list_sitemap`/`view_request`).
- White-box mode is detectable from target type (`infer_target_type` → `repository`/`local_code`) and the clone path; black-box mode simply omits the code collector and reachability seam.
- "Volatile" path segments (numeric/UUID IDs) are templatable by a deterministic ruleset; perfect a-priori path schemas are not assumed.

**Risks**
- **Classification is agent-proposed → can be wrong.** Mitigated by the §1-principle-2 split: a wrong class only mis-targets a *deterministic* spray (recoverable, cheap), it never fabricates a "confirmed" finding. Classification determinism is asserted as a PBT invariant (same evidence ⇒ same class).
- **Over-merging in dedup** (two genuinely-different endpoints collapsed) → mitigated by a conservative normalizer (only declared canonicalization rules) and the **dedup-idempotence** + **provenance-completeness** invariants; every merge records the union of sources for audit.
- **Scoring drift / non-monotonic ranking** (adding signal lowers a score) → mitigated by the **scoring-monotonicity** invariant (strictly more attack-surface signals ⇒ never a lower score).
- **False reachability** (sink reported reachable when no path exists) → mitigated by the **reachability-soundness** invariant: a flagged sink carries a concrete path or is marked unreachable; "unknown" is allowed but distinct from "reachable."
- **Framework-parser sprawl** (chasing every stack) → explicitly bounded to top-5 stacks; long tail deferred to the agent (program out-of-scope, §6 anti-pattern).
- **Recon-as-finding** (treating a sprayed candidate as a confirmed bug) → Phase 3 emits *candidates only*; exploitation and impact-gating live downstream.
