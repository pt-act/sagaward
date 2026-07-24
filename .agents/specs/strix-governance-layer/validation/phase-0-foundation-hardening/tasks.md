# Phase 0 — Foundation & Quick Wins · Tasks (Breakdown)

> Spec-Architect PBT variant · Phase 3 output. Status syntax: `- [ ] not_started`, `- [~] in_progress`, `- [x] completed`, `- [-] blocked`.
> Estimates in **iterations**, never hours/days. Total focused tests target: **16–34**. Feature target: **~3 iterations**.

---

## Overview

Four task groups, mapped to advice **#11 / #12 / #6 / #10**:

| Group | Theme | Advice | Primary files | Security-critical? |
|---|---|---|---|---|
| **G1** | Toolchain bundling + structured runner | #11 | `containers/Dockerfile`, `pyproject.toml`, `strix/tools/` | No (Tier 1) |
| **G2** | Import-side-effect reduction | #12 | `strix/interface/utils.py`, `tests/` | No (Tier 1) |
| **G3** | Outbound-trust hardening (`strix/core/net/`) | #6 | `strix/core/net/`, `strix/interface/utils.py` | **Yes (Tier 1 + Tier 2 PBT)** |
| **G4** | Impact-gated severity policy | #10 | `strix/report/state.py`, `strix/tools/reporting/tool.py` | **Yes (Tier 1 + Tier 2 PBT)** |

Focused-test budget allocation: G1 = 4, G2 = 4, G3 = 8, G4 = 6 → **22 focused tests** (within 16–34). Tier-2 PBT adds property suites for G3 and G4.

---

## Group 1 — Toolchain bundling + structured runner (#11)

### Implementation
- [ ] 1.1 Pin `gitleaks`, `trufflehog`, `trivy` to explicit versions in `containers/Dockerfile` (replace `latest`/HEAD installs at 134–150) (not_started)
- [ ] 1.2 Add `ruff` (align to `pyproject.toml` pin) and `pytest` to the image on the `pentester` `PATH` (not_started)
- [ ] 1.3 Add build-time self-check stage failing the build if any of the five is missing/off-PATH (not_started)
- [ ] 1.4 Add deterministic scanner-runner tool in `strix/tools/` (registered alongside `shell`/`reporting`) returning `{tool, version, target, findings[], raw_output_ref}` (not_started)
- [ ] 1.5 Add scanner availability/version query for the agent (not_started)

### Validation Tier 1 (focused — 4)
- [ ] 1.6 Self-check fails when a required tool is absent (1 test) (not_started)
- [ ] 1.7 Scanner-runner returns structured dict with expected keys for a known scanner (1 test) (not_started)
- [ ] 1.8 Scanner-runner references raw output rather than inlining stdout (1 test) (not_started)
- [ ] 1.9 Availability query lists the five scanners + versions (1 test) (not_started)

### Security Readiness Checklist
- [ ] 1.10 Pinned versions, no `latest` for the five (not_started)
- [ ] 1.11 Runner does not pass unsanitized agent input into shell concatenation (argv form) (not_started)
- [ ] 1.12 Raw-output pointers stay within run-dir boundary (no traversal) (not_started)

---

## Group 2 — Import-side-effect reduction (#12)

### Implementation
- [ ] 2.1 Convert eager `import docker` / `from docker.errors` (utils.py:17–18) to lazy imports inside `check_docker_connection`/`image_exists` (not_started)
- [ ] 2.2 Ensure pure validators (`validate_repo_url`, target parsing) import with no Docker/network side effects (not_started)
- [ ] 2.3 Verify `tests/test_core_paths.py` still passes; add a direct-import path for new tests (not_started)

### Validation Tier 1 (focused — 4)
- [ ] 2.4 `from strix.interface.utils import validate_repo_url` succeeds with `docker` unavailable (mock import failure) (1 test) (not_started)
- [ ] 2.5 Importing the module triggers no network I/O (1 test) (not_started)
- [ ] 2.6 `check_docker_connection` still works when `docker` IS available (back-compat) (1 test) (not_started)
- [ ] 2.7 Existing `test_core_paths.py` suite remains green (regression guard) (1 test) (not_started)

### Security Readiness Checklist
- [ ] 2.8 No secrets/daemon connection attempted at import time (not_started)
- [ ] 2.9 Lazy-import failure path surfaces the existing clear Docker error (not_started)

---

## Group 3 — Outbound-trust hardening · `strix/core/net/` (#6) — SECURITY-CRITICAL

### Implementation
- [ ] 3.1 Create `strix/core/net/` with URL normalization (canonical scheme/host/port/path, idempotent) (not_started)
- [ ] 3.2 Alternate IP-notation decoding (decimal/octal/hex IPv4, IPv4-mapped & compressed IPv6) (not_started)
- [ ] 3.3 Internal/metadata classifier (loopback, RFC-1918, link-local, CGNAT, ULA, metadata endpoints) generalizing `_is_localhost_host` (utils.py:1215) (not_started)
- [ ] 3.4 Curated corpora: internal-CIDR + cloud-metadata (canonical + alternate), external-public control set (not_started)
- [ ] 3.5 Redirect-chain revalidation wrapping the `_is_http_git_repo` (utils.py:1051) `urlopen` path; re-normalize+re-classify every hop (hop cap + timeout) (not_started)
- [ ] 3.6 OOB-confirmation hook seam (null default; documented Phase 2 plug-in point) (not_started)
- [ ] 3.7 Wire net validators into the clone/target path without breaking `rewrite_localhost_targets` (1233) (not_started)

### Validation Tier 1 (focused — 8)
- [ ] 3.8 Normalization strips default port + lowercases host (1) (not_started)
- [ ] 3.9 Decimal IP (`2130706433`) decodes to loopback and is rejected (1) (not_started)
- [ ] 3.10 Octal/hex IPv4 internal forms rejected (1) (not_started)
- [ ] 3.11 `169.254.169.254` metadata endpoint rejected (1) (not_started)
- [ ] 3.12 IPv4-mapped IPv6 internal form rejected (1) (not_started)
- [ ] 3.13 External public target accepted (no false positive) (1) (not_started)
- [ ] 3.14 Redirect external→internal is rejected; external→external passes (1) (not_started)
- [ ] 3.15 OOB seam null impl returns "no confirmation available" with no side effect (1) (not_started)

### Validation Tier 2 (PBT — security-critical)
- [ ] 3.16 PBT **SP-1** normalization idempotence over generated URLs (not_started)
- [ ] 3.17 PBT **SP-2** notation-invariant classification (differential vs `ipaddress`) (not_started)
- [ ] 3.18 PBT **SP-3** internal/metadata rejection completeness + external acceptance over corpora (not_started)
- [ ] 3.19 PBT **SP-4** redirect-chain safety: any internal hop ⇒ rejected (not_started)

### Security Readiness Checklist
- [ ] 3.20 No bypass: corpora cover all notations × all internal ranges (not_started)
- [ ] 3.21 Redirect hop cap prevents loops; per-hop timeout enforced (not_started)
- [ ] 3.22 Module ≤ 400 lines / single-responsibility (split if needed) (not_started)

---

## Group 4 — Impact-gated severity policy (#10) — SECURITY-CRITICAL

### Implementation
- [ ] 4.1 Add `evidence_class ∈ {diff, callback, reachability, none}` to the report record (`report/state.py::add_vulnerability_report`, record at line 162) (not_started)
- [ ] 4.2 Implement the impact gate: `none` ⇒ down-grade severity to unconfirmed; non-`none` ⇒ keep CVSS-derived severity (hook after `_calculate_cvss`, reporting/tool.py:214) (not_started)
- [ ] 4.3 Record gate decision + evidence class on the persisted record (glass-box) (not_started)
- [ ] 4.4 Default evidence class to `none` so existing callers are gated until Phases 1–3 supply evidence (not_started)

### Validation Tier 1 (focused — 6)
- [ ] 4.5 CVSS-high finding with `evidence_class=none` is down-graded (1) (not_started)
- [ ] 4.6 Finding with `evidence_class=diff` keeps CVSS severity (1) (not_started)
- [ ] 4.7 Finding with `evidence_class=callback` keeps CVSS severity (1) (not_started)
- [ ] 4.8 Evidence class + gate decision persisted on record (1) (not_started)
- [ ] 4.9 Down-graded finding stays visible (not dropped) (1) (not_started)
- [ ] 4.10 Back-compat: existing reporting-tool happy path still produces a report (1) (not_started)

### Validation Tier 2 (PBT — security-critical)
- [ ] 4.11 PBT **SP-6** gate monotonicity: `none → severity ≤ unconfirmed`; non-`none → severity = cvss-derived`, over generated findings (not_started)

### Security Readiness Checklist
- [ ] 4.12 No path lets `evidence_class=none` report at full severity (not_started)
- [ ] 4.13 Gate decision is inspectable and not silently dropping data (not_started)

---

## Dependency Mapping

```
G1 (toolchain)      ── independent ──┐
G2 (import hygiene) ── independent ──┤
                                     ├─► G3 (net) depends on G2 (clean imports for net validators)
G4 (impact gate)    ── independent ──┘   G3.7 wiring depends on G2.1–2.2
```

- **G3 depends on G2** (net validators must import without `docker`/network — the whole point of #12).
- **G1, G2, G4 are mutually independent** and can start in parallel.
- Within G3: 3.1 → 3.2 → 3.3 → 3.4 → 3.5; 3.6 independent; 3.7 last (integration).
- Within G4: 4.1 → 4.2 → 4.3; 4.4 after 4.2.

### Critical path
`G2 (import hygiene) → G3 (net hardening, incl. PBT)` — the longest chain and the security-critical spine. G1 and G4 ride alongside.

---

## Parallelization Strategy

| Devs | Allocation |
|---|---|
| **1 dev** | Iteration 1: G2 + G1 (independent, fast). Iteration 2: G3 (net + Tier-1 + PBT). Iteration 3: G4 + gap-fill + full-suite green. |
| **2 devs** | Dev A: G2 → G3 (critical path). Dev B: G1 ∥ then G4. Sync at end of iteration 2; both close gaps in iteration 3. |

Efficiency: G1/G2/G4 independence lets a second dev shave ~1 iteration off the critical path. No frontend components (all backend/build), so no 400-line UI constraint applies; `strix/core/net/` held ≤ 400 lines (3.22).

---

## Iteration Estimates

- **Iteration 1** — G1 (toolchain pin + self-check + runner) and G2 (import hygiene) with their Tier-1 tests.
- **Iteration 2** — G3 (`strix/core/net/` build-out, Tier-1 + Tier-2 PBT SP-1…SP-4).
- **Iteration 3** — G4 (impact gate + SP-6 PBT), gap-filling (≤10 extra tests if needed), full regression + `test_core_paths.py` green.

**Total: ~3 iterations** (≈2.5 with 2 devs). Focused tests: **22** (G1 4 · G2 4 · G3 8 · G4 6), within the 16–34 budget; PBT suites cover SP-1…SP-4 and SP-6.

---

## Exit Criteria (from roadmap Phase 0)

- [ ] Scanners run inside the sandbox and feed **structured** results to the agent (G1).
- [ ] Dangerous-boundary modules are unit-testable in isolation (G2).
- [ ] SSRF helper rejects normalized/alternate-notation internal + metadata targets, with regression + PBT (G3).
- [ ] Impact-gated severity policy explicit and inspectable in the report layer (G4).
- [ ] OOB-confirmation seam defined for Phase 2 (G3.6).
