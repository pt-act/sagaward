# Phase 0 — Foundation & Quick Wins · Specification

> Spec-Architect PBT variant · Phase 2 output. WHAT, not HOW — no code bodies.
> Maps to roadmap advice **#11, #12, #6 (partial), #10**. Primitive: **none** (enabler).
> Detailed analysis lives in `planning/requirements.md`.

---

## Goal

Make the strix foundation **reproducible, testable, hardened, and impact-honest** so Phases 1–5 build on solid ground. Concretely: bundle and pin the analysis toolchain with structured result wiring; remove import side effects that block isolated unit testing; extend outbound-trust hardening (normalization, alternate-notation + internal/metadata rejection, redirect revalidation, OOB-confirmation seam); and make the impact-gated severity policy explicit in the report layer.

---

## Architecture Overview

```mermaid
graph TD
    subgraph Sandbox image ["containers/ (sandbox image)"]
        TC["Pinned toolchain<br/>gitleaks · trufflehog · trivy · ruff · pytest"]
        SC["Build-time self-check"]
    end
    AG["strix agent"] -->|invokes| SR["Scanner-runner tool<br/>(strix/tools/, alongside shell/reporting)"]
    SR -->|runs in| TC
    SR -->|structured results| AG

    AG -->|target / clone| NET["strix/core/net/<br/>normalize · alt-notation decode<br/>internal+metadata classify · redirect revalidation"]
    NET -.->|OOB-confirmation seam (null in P0)| OOB["P3 OOB oracle (Phase 2)"]
    UTILS["strix/interface/utils.py<br/>(lazy docker import)"] --> NET

    AG -->|create finding| RPT["Reporting tool + report/state.py"]
    RPT --> GATE["Impact gate<br/>evidence-class ∈ {diff,callback,reachability,none}<br/>none ⇒ severity down-graded"]
    GATE --> REC["Report record (evidence_class recorded, inspectable)"]
```

---

## User Stories

1. **As the strix agent**, I want pinned scanners with structured output in my sandbox, so results are reproducible and machine-consumable.
2. **As a strix developer**, I want to `import` and unit-test dangerous-boundary validators with no Docker daemon or network.
3. **As a strix developer**, I want internal/metadata targets rejected across normalized and alternate notations, including across redirect hops.
4. **As a bounty operator**, I want evidence-less findings auto-down-graded so my attention lands on confirmed impact.
5. **As a Phase 2 implementer**, I want a defined OOB-confirmation seam so I can wire the real oracle in without re-plumbing SSRF.

---

## Specific Requirements

### Functional

| ID | Requirement | Success criteria |
|---|---|---|
| **F1** | Pin `gitleaks`, `trufflehog`, `trivy`, `ruff`, `pytest` to explicit versions in the image (and `pyproject.toml` for Python tools). | Image build references a fixed version for each of the five; `ruff` + `pytest` present on `pentester` `PATH`. |
| **F2** | Build-time self-check fails the image build if any required tool is missing or off `PATH`. | Removing/renaming any of the five causes the build to fail with a clear message naming the missing tool. |
| **F3** | Deterministic scanner-runner tool: runs a named scanner against a target/workspace and returns structured results `{tool, version, target, findings[], raw_output_ref}`. | Agent receives a structured dict (not free-form stdout); raw output is referenced, not inlined. |
| **F4** | Scanner availability/version is queryable by the agent. | Agent can list available scanners + versions without shelling out. |
| **F5** | `strix/interface/utils.py` + `strix/core/net/` import with **no** `docker` import and **no** network. | `from strix.interface.utils import validate_repo_url` and net validators import cleanly with `docker` absent; `tests/test_core_paths.py` still passes; new tests use direct imports. |
| **F6** | URL normalization: canonical scheme/host/port/path; idempotent. | `normalize(normalize(u)) == normalize(u)` for all inputs; default ports stripped; host lowercased. |
| **F7** | Alternate IP-notation decoding: decimal/octal/hex IPv4, IPv4-mapped & compressed IPv6. | Each alternate notation classifies identically to its canonical address. |
| **F8** | Internal-target rejection: loopback, RFC-1918, link-local, CGNAT, ULA, and cloud-metadata (`169.254.169.254`, GCP/Azure/`fd00:ec2::254`) across all notations. | Every corpus entry (canonical + alternate) is rejected; curated external public corpus is accepted. |
| **F9** | Redirect-chain revalidation: every hop re-normalized and re-classified. | A redirect from an external to an internal/metadata target is rejected even when the initial target is external. |
| **F10** | OOB-confirmation hook seam in `strix/core/net/`, null implementation in Phase 0. | Seam exists, defaults to "no confirmation available", and is the documented Phase 2 plug-in point; no behavior change in P0. |
| **F11** | Explicit impact gate in report layer: report carries `evidence_class ∈ {diff, callback, reachability, none}`; `none` down-grades severity. | A CVSS-high finding with `evidence_class=none` is recorded at a down-graded (unconfirmed) severity; evidence-backed findings keep their severity. |
| **F12** | Gate decision + evidence class recorded on the report record (glass-box). | `evidence_class` and the gate outcome are present and inspectable on the persisted report. |

### Non-Functional

| ID | Category | Requirement | Success criteria |
|---|---|---|---|
| **N1** | Reproducibility | Same image build ⇒ same tool versions. | Pinned versions; no `latest` for the five required tools. |
| **N2** | Testability | Dangerous-boundary modules unit-testable in isolation. | Net + validator tests run with no Docker, no network, < a few seconds. |
| **N3** | Security | SSRF rejection is complete across notations and redirect hops. | PBT (SP-2, SP-3) passes on internal/metadata corpora; zero corpus bypasses. |
| **N4** | Back-compat | No regression to existing CLI, clone, localhost-rewrite, or `test_core_paths.py`. | Existing suite green. |
| **N5** | Cohesion | `strix/core/net/` single-responsibility; no module > 400 lines. | Module review; split if approaching limit. |
| **N6** | Transparency | Impact-gate and scanner results inspectable. | Evidence class recorded; structured scanner output. |

---

## PBT Validation Strategy

### Focused-testing components (Tier 1)
- Toolchain bundling & self-check (build-time presence/version) — integration-style assertions.
- Scanner-runner result shape and availability query.
- Import-side-effect removal (importability without `docker`/network; back-compat).
- Impact-gate happy/edge paths (each evidence class → expected severity behavior).
- OOB seam null behavior.

### Property-based-testing components (Tier 2 — security-critical)
- **URL normalization** — idempotence + canonical-form invariants over generated URLs.
- **Alternate-notation IP decoding** — equivalence to canonical across decimal/octal/hex/IPv6 forms (differential vs. `ipaddress`).
- **Internal/metadata rejection** — completeness across notations; external-public acceptance.
- **Redirect-chain revalidation** — any hop landing internal ⇒ rejection.

---

## Security Properties to Validate (∀ invariants)

1. **SP-1 — Normalization idempotence:**
   `∀ url: normalize(normalize(url)) = normalize(url)`
2. **SP-2 — Notation-invariant classification:**
   `∀ ip, ∀ notation ∈ {decimal, octal, hex, ipv4-mapped-ipv6, compressed}: classify(decode(render(ip, notation))) = classify(ip)`
3. **SP-3 — Internal-target rejection completeness:**
   `∀ t ∈ (internal_cidr ∪ metadata_corpus), ∀ notation: is_internal(normalize(t)) = true` ⇒ outbound rejected
   and `∀ t ∈ external_public_corpus: is_internal(normalize(t)) = false`
4. **SP-4 — Redirect-chain safety:**
   `∀ chain = [h₀…hₙ]: (∃ hᵢ: is_internal(normalize(hᵢ))) → rejected(chain)`
5. **SP-5 — Import purity:**
   `∀ pure_validator v: import(v) ⇏ import(docker) ∧ import(v) ⇏ network_io`
6. **SP-6 — Impact-gate monotonicity:**
   `∀ finding f: evidence_class(f) = none → severity_out(f) ≤ severity_unconfirmed`
   and `∀ f: evidence_class(f) ≠ none → severity_out(f) = severity_from_cvss(f)`

---

## Existing Code to Leverage

- `strix/interface/utils.py` — `validate_repo_url` (1259), `_is_localhost_host` (1215), `rewrite_localhost_targets` (1233), `_is_http_git_repo` (1051, redirect path), `infer_target_type` (1063); eager `import docker` (17–18) + `check_docker_connection` (1366) to lazy-load.
- `strix/core/paths.py` — `validate_run_name`, `run_dir_for` (pure-helper pattern for net validators).
- `containers/Dockerfile` — unpinned `trufflehog`/`gitleaks`/`trivy` installs (134–150); `pipx`/`go install`/`npm` + `PATH` (167, 205) to extend with pins + `ruff`/`pytest` + self-check.
- `pyproject.toml` — `ruff>=0.11.13` (53), `[tool.ruff]` (111+) to pin/align.
- `strix/tools/` — tool registration surface (`shell`, `reporting`, `proxy`…) for the scanner-runner.
- `strix/runtime/docker_client.py` — `StrixDockerSandboxClient` sandbox lifecycle (where toolchain runs).
- `strix/tools/reporting/tool.py` — `_calculate_cvss` (122), `_do_create` (154) — impact-gate hook point.
- `strix/report/state.py` — `add_vulnerability_report` (139), report record (162) — evidence-class field + gate.
- `tests/test_core_paths.py` — unittest pattern (14–23) to mirror; motivating evidence for #12.

---

## Out of Scope

- **Real OOB oracle (P3)** — Phase 2. Phase 0 ships only the null seam.
- **Diff (P2) / reachability (P4) evidence producers** — Phases 1 and 3. Phase 0's gate only *honors* them when present.
- **White-box / source-to-runtime SSRF correlation** — cross-cutting (P4).
- **New scanners beyond the five named** — not added here.
- **Bounty-mode strategy layer, finding-memory, long-tail framework parsers** — program-level out of scope.

---

## Quality Gate 1 (design-principle alignment)

| Question | Answer |
|---|---|
| **Does this enhance human capability?** | Yes — reproducible structured tooling + impact-gating amplify the operator and the agent; no judgement is removed. |
| **Does it support focus / avoid distraction?** | Yes — impact-gating down-grades evidence-less noise; tighter SSRF rejection prevents wasted internal-target chases. |
| **Is the system transparent (glass-box)?** | Yes — pinned versions, structured scanner results, recorded `evidence_class`, and an inspectable gate decision. |

**Gate 1: PASS.** Proceed to `tasks.md`.
