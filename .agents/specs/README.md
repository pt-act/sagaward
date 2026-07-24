# Strix Bounty-Grade Engine — Program Specs

> Spec-Architect program index. "Deep thinking before building."
> Source roadmap: `strix-bounty-roadmap.md`. Format: Spec-Architect PBT variant (Orion-OS 3-phase + PBT validation gate).

This program turns strix from breadth-oriented automation into a stateful, auth-aware, impact-gated bounty engine. It is decomposed into **six feature specs**, each a self-contained Spec-Architect unit (`planning/requirements.md` → `spec.md` → `tasks.md`).

---

## Program goal

Raise the ceiling on *meaningful* findings (IDOR, broken function-level auth, business-logic, SSRF, race conditions) by giving the strix agent durable, composable primitives instead of one-shot scans — and gate every reported finding on demonstrated impact.

---

## Program Quality Gate 1 (design-principle alignment)

| Question | Program answer |
|---|---|
| Does this enhance human capability? | Yes — it amplifies a human bounty hunter's reach (stateful auth testing, OOB confirmation, differential analysis) rather than replacing judgement. |
| Does it support focus / avoid distraction? | Yes — impact-gating and reachability filtering reduce noise so the operator's attention lands on real findings, not scanner spew. |
| Is the system transparent (glass-box)? | Yes — every finding carries evidence (a diff, a callback, a reachability path); the agent proposes, deterministic harnesses verify, and the trail is inspectable. |

**Gate 1: PASS** at program level. Each feature spec re-validates Gate 1 locally.

---

## The four primitives (shared vocabulary)

Most features are emergent properties of these. Specs reference them by ID.

| ID | Primitive | Owning feature spec |
|---|---|---|
| **P1** | Identity / session state — durable multi-identity store, import/export, replay | Phase 1 |
| **P2** | Differential engine — semantic response diffing across identity/verb/token/state/header | Phase 1 |
| **P3** | OOB oracle — interactsh-style listener + per-finding callback-token correlation | Phase 2 |
| **P4** | Reachability map — route → handler → auth middleware → sink graph (white-box mode) | Cross-cutting (Phase 3 / combined mode) |

---

## Feature spec index

| Spec | Feature | Primitives | Est. (iterations) | Critical path? |
|---|---|---|---|---|
| `phase-0-foundation-hardening/` | Toolchain bundling, import testability, SSRF/outbound hardening | — | 3 | Enabler |
| `phase-1-identity-differential/` | Multi-role authenticated replay + differential (F1) | P1 + P2 | 8 | **Yes — gate** |
| `phase-2-oob-oracle/` | Native OOB support (F2) | P3 | 5 | High |
| `phase-3-attack-surface-inventory/` | Unified endpoint/parameter inventory (F3) | feeds all | 7 | High |
| `phase-4-race-harness/` | Race condition harness (F4) | P1 + P2 | 4 | Parallel w/ P3 |
| `phase-5-business-logic-testing/` | Business-logic state testing (F5) | all + F3 | 9 | Terminal |

*Estimates are in iterations, never hours/days (Spec-Architect rule).*

---

## Cross-phase dependency graph

```
Phase 0 (foundation)
   │
   ▼
Phase 1 (P1 identity + P2 differential)  ◀── critical-path gate; nothing reaches its ceiling without it
   │
   ├──────────────┬───────────────┐
   ▼              ▼               ▼
Phase 2 (OOB)  Phase 3 (inventory)  Phase 4 (race)   ◀── Phase 3 & 4 can run in parallel
   │              │               │
   └──────────────┴───────┬───────┘
                          ▼
              Phase 5 (business-logic)   ◀── consumes P1+P2+P3 + race harness
```

**Critical path:** `0 → 1 → 3 → 5` (longest dependency chain). Phases 2 and 4 are front-loaded deliberately because they most reduce false positives, which matters more for an LLM agent than for a human-driven scanner.

---

## Global conventions (apply to every spec in this program)

- **Estimates in iterations, never time.** An "iteration" is one focused implement-test-review loop.
- **Task status syntax:** `- [ ] not_started`, `- [~] in_progress`, `- [x] completed`, `- [-] blocked`, numbered `Group.Task` (e.g. `1.2`).
- **Focused testing budget:** 2–8 tests per task group, max 10 additional for gap-filling, **16–34 tests per feature** total. Security-critical components additionally get Tier-2 Property-Based Testing.
- **Security properties are invariants.** Expressed as `∀ ...` logical statements, validated as PBT properties before the security-audit gate.
- **Component size:** TUI/frontend components capped at 400 lines; backend modules kept cohesive and single-responsibility.
- **WHAT, not HOW.** Specs describe behavior and contracts, not implementations. No code bodies in `spec.md`.
- **Impact-gating is non-negotiable.** A finding is reportable only with evidence: a P2 diff, a P3 callback, or a P4 reachability/state result.

---

## Existing strix code to leverage (reuse before build)

Verified modules in the current repo that the specs reference as integration points:

- `strix/interface/utils.py` — `clone_repository`, `validate_run_name`, `validate_repo_url` (landed on `fix/run-path-and-clone-hardening`), target parsing, localhost→gateway URL rewriting. Anchor for SSRF hardening (Phase 0) and reachability seeding (P4).
- `strix/tools/proxy/` — existing proxy tool / traffic interception. Anchor for identity capture (P1), inventory extraction (P3), and replay.
- `strix/runtime/docker_client.py` + `containers/` — sandbox lifecycle. Anchor for the OOB sidecar (P3) and bundled toolchain (Phase 0).
- `strix/report/state.py` — `ReportState`, `vulnerability_reports`, severity handling. Anchor for impact-gating.
- `strix/core/{paths,runner,inputs}.py` — run orchestration and path helpers.
- `strix/tools/{agents_graph,web_search,notes,todo,thinking,finish}/` — agent tool surface that new tools (replay, diff, oob, inventory, race) plug into.
- `tests/test_core_paths.py` — existing regression-test pattern (unittest + spec-loaded module) to mirror.

---

## Out of scope (program level)

Deferred from the source roadmap; not specced here.

- **Bounty-mode strategy layer (advice #13)** — a prioritization *policy*, nearly free once P1–P4 exist; configured later, not a build item.
- **Cross-target finding-memory (advice #14)** — deferred to avoid confirmation bias; only per-engagement memory is in scope within individual specs.
- **Long-tail framework parsers (advice #9)** — Phase 3 covers the top stacks only (FastAPI, Flask/Django, Express/NestJS, Next.js, GraphQL); the rest is left to agent reasoning.
- **Full multi-phase implementation in one pass** — each spec is independently schedulable.

---

## Directory map

```
specs/
├── README.md                              # this index
├── phase-0-foundation-hardening/
│   ├── planning/requirements.md
│   ├── spec.md
│   └── tasks.md
├── phase-1-identity-differential/
│   ├── planning/requirements.md
│   ├── spec.md
│   └── tasks.md
├── phase-2-oob-oracle/            { planning/requirements.md, spec.md, tasks.md }
├── phase-3-attack-surface-inventory/   { planning/requirements.md, spec.md, tasks.md }
├── phase-4-race-harness/          { planning/requirements.md, spec.md, tasks.md }
└── phase-5-business-logic-testing/     { planning/requirements.md, spec.md, tasks.md }
```

---

*Spec-Architect program index. Each feature spec re-runs Gate 1 locally and carries its own PBT validation strategy.*
