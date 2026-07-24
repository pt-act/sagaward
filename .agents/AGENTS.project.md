# AGENTS.project.md — Strix

## Extends
AGENTS.md v2.4.9 (base)

## Deviations

### §03 · Code Editing
- **Language:** Python 3.12+ (not TypeScript/Next.js).
- **File limit:** 400 lines remains the cap; backend modules stay cohesive and single-responsibility.
- **Type checking:** Strict mypy + Pyright. No `any` unless the value can truly be any type.
- **Linter:** Ruff with the project's selected rule sets (see `pyproject.toml` `[tool.ruff]`); never disable rules globally without a per-file-override entry.
- **Formatting:** Ruff formatter (Black-compatible), 100-character line length, double quotes, 4-space indentation.
- **Security linting:** Bandit is enabled; do not introduce new `B` skips without discussion.
- **Imports:** `strix` is first-party; `pydantic` is third-party. Use explicit `from __future__ import annotations` where needed for forward references.
- **Lazy imports:** Some existing modules use lazy imports inside functions to avoid circular dependencies with telemetry/report/dedupe/CVSS. New code should avoid introducing new circular dependencies; if a lazy import is required, document why in a comment.
- **Docker coupling:** `docker` must be imported lazily in pure validators so they remain unit-testable without a Docker daemon (see Phase 0 SP-5).

### §06 · Frontend & Design
- **Stack:** Textual TUI (not web). TUI components are capped at 400 lines; warn at 350.
- **UI states:** Every interactive element must have real behavior, including loading, empty, and error states.

### §09 · Session & Memory
- **Memory bank:** `.agents/memory_bank/` follows `MEMORY_FORMATS.md`. PROGRESS.md is the human's development diary; do not prune it unilaterally.
- **Specs program:** `.agents/specs/` is the source of truth for the bounty-grade engine roadmap. Implementation follows the manifest DAG and the spec files.

### §11 · Conditional Overlays
- **Security tooling overlay:** This project builds offensive security tools. Always verify scope, never auto-attack non-owned targets, and gate every finding on demonstrated impact (diff, callback, or reachability/state evidence).
- **Docker sandbox overlay:** Many tests need the sandbox container. Use the existing `tests/test_core_paths.py` pattern for pure unit tests; integration tests rely on the container lifecycle in `strix/runtime/docker_client.py`.

## Never Do This
> **Never:** Import `docker` eagerly in URL/network validators or pure utility modules.
> **Why:** Phase 0 hardening requirement — these modules must be unit-testable without Docker or network.

> **Never:** Add a new security finding without a recorded `evidence_class` in `report/state.py`.
> **Why:** Impact-gating is non-negotiable; evidence-less findings are auto-down-graded.

> **Never:** Re-implement a primitive that already exists in an earlier phase (P1 identity, P2 diff, P3 OOB, Phase 4 race harness, Phase 3 inventory).
> **Why:** The spec program is built on reuse; re-implementation creates divergence and double maintenance.

> **Never:** Confirm a blind vulnerability without a correlated OOB callback or deterministic differential artifact.
> **Why:** The agent proposes; the harness disposes. Model self-confirmation is a locus-1 failure.
