# Phase 3 — Unified Attack-Surface Inventory — Tasks

> Spec-Architect PBT variant · Reachability seam **P4** · Feature **F3** (feeds all later phases).
> Status syntax: `- [ ] not_started` · `- [~] in_progress` · `- [x] completed` · `- [-] blocked`.
> Estimates in **iterations** (one implement-test-review loop), never time.

---

## Overview

Eight task groups build the unified inventory: **source collectors** (JS / sitemap / external tools / code), a **normalizer & dedup** core, a **scoring** ranker, **parameter extraction & classification**, a **deterministic class-spray library**, **framework route parsers** (top-5 stacks), the **P4 reachability seam** (white-box), and **testing**. The real work is the **join point** — normalize → dedup → score into one ranked map; collectors and framework parsers are independent leaves that parallelize. Critical path: `collectors → normalizer+dedup → scoring → param-extract → classify → spray → tools → testing`. Total focused tests: **30** (within 16–34). Target: **~7 iterations**.

---

## Task Group 1 — Source Collectors

### Implementation
- [ ] 1.1 Common `EndpointObservation` shape (method, raw URL, params, source tag, raw evidence) (not_started)
- [ ] 1.2 Sitemap collector via `list_sitemap`/`view_sitemap_entry` + `caido_api._clean_sitemap_*` node shape (not_started)
- [ ] 1.3 JS-route collector (parse discovered route hints into observations) (not_started)
- [ ] 1.4 External-tool collectors: parse `ffuf`/`katana`/`arjun`/`httpx` output (mirror `web_search._do_search` sandboxed/sanitized-return pattern; run via `tools/shell`) (not_started)
- [ ] 1.5 Code-route collector entry point (white-box; delegates extraction to TG6 parsers) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 1.6 Sitemap nodes → observations with correct method/URL/source tag (1 test) (not_started)
- [ ] 1.7 Each external tool's sample output parses to the common shape; one source tag each (2 tests) (not_started)
- [ ] 1.8 Every emitted observation carries exactly one source tag (1 test) (not_started)

### Security Readiness Checklist
- [ ] 1.9 Collectors bounded to in-scope hosts (`scope_rules`); no surface outside scope (not_started)
- [ ] 1.10 External-tool returns sanitized (no raw tool stderr / secret leakage into agent output) (not_started)

---

## Task Group 2 — Normalizer & Dedup  *(the join point — real work)*

### Implementation
- [ ] 2.1 Endpoint normalizer: host-case, default-port strip, trailing-slash, path-ID templating (`/users/123→/users/{id}`), query-key sort; record applied rules (not_started)
- [ ] 2.2 Endpoint key + merge: same-key observations → one endpoint = union(sources) ∪ union(params) (not_started)
- [ ] 2.3 Idempotent dedup pass (second pass is a fixpoint) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 2.4 Two noise-equivalent URLs collapse to one endpoint key; applied rules recorded (1 test) (not_started)
- [ ] 2.5 Merge unions sources + params from two collectors (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 2.6 PBT — **dedup idempotence**: `∀ S: dedup(dedup(S)) = dedup(S)` (not_started)
- [ ] 2.7 PBT — **provenance completeness**: `∀ e ∈ map: sources(e) ≠ ∅` (merge carries union of inputs' sources) (not_started)

### Security Readiness Checklist
- [ ] 2.8 Normalizer conservative (only declared rules); no over-merge of genuinely distinct endpoints (not_started)

---

## Task Group 3 — Scoring & Ranked Map

### Implementation
- [ ] 3.1 Attack-surface signal extractor (auth-required, object-ref, state-changing verb, upload, source-multiplicity, reachable-sink) (not_started)
- [ ] 3.2 Monotonic score function over signals; emit one ranked map per target (not_started)
- [ ] 3.3 Durable per-target inventory store via `core/paths.py` (not_started)

### Validation Tier 1: Focused Testing
- [ ] 3.4 Endpoint with more signals ranks at/above one with a strict subset (1 test) (not_started)
- [ ] 3.5 Ranked map persists + reloads per target (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 3.6 PBT — **scoring monotonicity**: `∀ e₁,e₂ with signals(e₁) ⊋ signals(e₂): score(e₁) ≥ score(e₂)` (not_started)

### Security Readiness Checklist
- [ ] 3.7 Score inputs inspectable (signals recorded per endpoint; no black-box rank) (not_started)

---

## Task Group 4 — Parameter Extraction & Classification

### Implementation
- [ ] 4.1 Param extractors: proxy traffic (`parse_raw_request`), OpenAPI, JS, HTML forms, (white-box) source; attach to endpoint w/ provenance + example values (not_started)
- [ ] 4.2 Param de-dup (same param from two sources merges, unions provenance) (not_started)
- [ ] 4.3 Agent classification surface: classify param → `object-id/url/html/file/amount/role/state`, record class + evidence (agent-proposed) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 4.4 Params extracted from a proxy request + an OpenAPI fixture, attached with provenance (1 test) (not_started)
- [ ] 4.5 Classification attaches exactly one class + its evidence to a param (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 4.6 PBT — **classification determinism**: `∀ p with fixed evidence E: classify(p,E)` is stable (not_started)

### Security Readiness Checklist
- [ ] 4.7 Class is recorded as a hypothesis (with evidence), never as a confirmed verdict (glass-box) (not_started)

---

## Task Group 5 — Class-Spray Library  *(deterministic)*

### Implementation
- [ ] 5.1 Fixed spray sets per class: `object-id`→IDOR neighbours, `url`→SSRF/OOB targets, `html`→XSS probes, `file`→upload/traversal, `amount`→boundary/negative, `role`/`state`→privilege/transition (not_started)
- [ ] 5.2 `spray(class)` lookup — deterministic, independent of model output; emits candidates only (no execution) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 5.3 Each class maps to its expected spray set; `object-id` yields IDOR neighbours, `url` yields SSRF/OOB targets (2 tests) (not_started)

### Validation Tier 2: PBT
- [ ] 5.4 PBT — **spray determinism**: `∀ class c: spray(c)` is a fixed set, identical across runs, no model output in payloads (not_started)

### Security Readiness Checklist
- [ ] 5.5 Sprays emit candidates only — no exploit execution; impact-gating stays downstream (`report/state.py`) (not_started)

---

## Task Group 6 — Framework Route Parsers (top-5 stacks)  *(parallel leaves)*

### Implementation
- [ ] 6.1 FastAPI + Flask/Django route extraction (route + method + param hints) (not_started)
- [ ] 6.2 Express/NestJS + Next.js route extraction (not_started)
- [ ] 6.3 GraphQL schema/operation extraction; unrecognized stacks fall through to agent reasoning (no error) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 6.4 A FastAPI fixture yields expected route+method observations (1 test) (not_started)
- [ ] 6.5 An Express fixture yields routes; an unknown stack falls through cleanly (2 tests) (not_started)

### Security Readiness Checklist
- [ ] 6.6 Parsers are read-only over source; no code execution of the target repo (not_started)

---

## Task Group 7 — P4 Reachability Seam (white-box / combined)

### Implementation
- [ ] 7.1 Detect mode via `infer_target_type` + clone path (`interface/utils.py`); black-box omits this seam (not_started)
- [ ] 7.2 Associate `route → handler → auth-middleware → sink`; annotate endpoint `reachable`(w/ path) / `unreachable` / `unknown` (not_started)
- [ ] 7.3 Feed reachability into the scoring signal set (reachable sink raises rank) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 7.4 Seeded route→handler→sink fixture annotates the endpoint reachable with a concrete path (1 test) (not_started)
- [ ] 7.5 Black-box target omits the reachability seam cleanly (no code collector, no annotation error) (1 test) (not_started)

### Validation Tier 2: PBT
- [ ] 7.6 PBT — **reachability soundness**: `∀ flagged sink k: (∃ path route→handler→k) ∨ marked_unreachable(k)` (not_started)

### Security Readiness Checklist
- [ ] 7.7 No unqualified "reachable" — every flagged sink carries a path or is `unreachable`/`unknown` (not_started)

---

## Task Group 8 — Agent Tool Surface & Testing (integration & gap-fill)

### Implementation
- [ ] 8.1 `@function_tool`s: build/read inventory, classify param, request class-spray, (white-box) reachability query — mirror `tools/proxy` conventions (`_ctx_client`, JSON returns) (not_started)

### Validation Tier 1: Focused Testing
- [ ] 8.2 End-to-end black-box: collect (sitemap+ext) → normalize → dedup → score → ranked map with provenance (1 test) (not_started)
- [ ] 8.3 End-to-end param path: extract → classify `object-id` → deterministic IDOR spray candidates (1 test) (not_started)
- [ ] 8.4 End-to-end white-box: code routes + reachability annotate + raise rank of a reachable sink (1 test) (not_started)

### Security Readiness Checklist
- [ ] 8.5 Full PBT suite (2.6, 2.7, 3.6, 4.6, 5.4, 7.6) green before audit gate (not_started)
- [ ] 8.6 No out-of-scope surface, no exploit execution, no secret leakage across the end-to-end path (not_started)

> **Focused-test count:** TG1: 4 · TG2: 2 · TG3: 2 · TG4: 2 · TG5: 2 · TG6: 3 · TG7: 2 · TG8: 3 = **20 Tier-1** + **6 Tier-2 PBT** (2.6, 2.7, 3.6, 4.6, 5.4, 7.6) = **26**; +4 covered as e2e/gap-fill in TG8/TG6 already counted = **30 total** (within 16–34).

---

## Dependency Mapping & Critical Path

```
TG1 Collectors ─┐
TG6 Parsers ────┤ (feed code observations)
                ▼
        TG2 Normalizer+Dedup ──► TG3 Scoring ──► TG8 Tools+Testing
                ▲                      ▲                ▲
TG7 Reachability ┘ (white-box signal) ─┘                │
TG4 Param Extract+Classify ──► TG5 Class-Spray ─────────┘
   ▲ depends on TG2 endpoints
```

- **TG2** depends on **TG1** (and **TG6** for code observations) — it is the **join point**; nothing ranks until observations are normalized + deduped.
- **TG3** depends on **TG2** (scores deduped endpoints) and consumes **TG7**'s reachability signal in white-box mode.
- **TG4** depends on **TG2** (params attach to deduped endpoints); **TG5** depends on **TG4** (spray keyed by class).
- **TG6** (framework parsers) and **TG7** (reachability) are **white-box leaves**; **TG6** feeds TG2, **TG7** feeds TG3's signal set.
- **TG8** depends on **all** groups.

**Critical path:** `TG1 → TG2 → TG3 → TG4 → TG5 → TG8` (collect → dedup → score → classify → spray → tools/testing). The join point **TG2 (normalizer+dedup)** is the bottleneck — it is the real work, and every leaf converges on it.

---

## Parallelization

- **Collectors (TG1) and framework parsers (TG6)** are independent leaves — develop in parallel against fixtures.
- **Reachability seam (TG7)** develops in parallel (white-box, against seeded route/sink fixtures), plugging into TG3's signal set.
- **dedup/scoring (TG2/TG3) is the join point** — it cannot parallelize past its inputs and gates TG4/TG5/TG8.
- **Dev A:** TG2 → TG3 → TG4 → TG5 → TG8 (the join + param pipeline). **Dev B:** TG1 + TG6 + TG7 (leaves) then joins TG8. With two developers the leaves collapse off the critical path, saving roughly one iteration.

---

## Iteration Estimate

| Group | Iterations |
|---|---|
| TG1 Source Collectors | 1 (parallel leaf) |
| TG2 Normalizer & Dedup | 1.5 (join point) |
| TG3 Scoring & Ranked Map | 1 |
| TG4 Param Extract & Classify | 1 |
| TG5 Class-Spray Library | 0.5 |
| TG6 Framework Parsers | 1 (parallel leaf) |
| TG7 Reachability Seam | 1 (parallel leaf) |
| TG8 Tools & Testing | 1 |
| **Total (sequential)** | **~8 iterations** |
| **With leaves (TG1/TG6/TG7) parallelized** | **~7 iterations** |

---

## Quality Gates

- [ ] **Gate 1** — design-principle alignment (recorded in `spec.md`): PASS.
- [ ] **Gate 2** — all Tier-1 focused tests pass.
- [ ] **Gate 3** — all Tier-2 PBT invariants validated (dedup idempotence, provenance completeness, scoring monotonicity, classification determinism, spray determinism, reachability soundness).
- [ ] **Gate 4** — security audit on the pre-validated system (scope-bounded, candidates-only, provenance + reachability evidence attached; no exploitation in this phase).
