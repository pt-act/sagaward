# Phase 0 — Foundation & Quick Wins · Requirements (Planning)

> Spec-Architect PBT variant · Phase 1 output (Shape the Spec).
> Source roadmap: `strix-bounty-roadmap.md` §4 Phase 0, advice items **#11, #12, #6 (partial), #10**.
> Program index: `specs/README.md`. This is the **enabler** spec — no new primitive (P1–P4); it de-risks every later phase.

---

## 1. Problem & intent

Strix today is a breadth-oriented LLM scanner whose foundation has four concrete friction points that slow every downstream feature and weaken finding quality:

1. **Toolchain drift.** The analysis tools the agent and CI depend on (`gitleaks`, `trufflehog`, `trivy`, `ruff`, `pytest`) are inconsistently present. `gitleaks`, `trufflehog`, and `trivy` are installed ad-hoc in `containers/Dockerfile` (lines 134–150) but are **not pinned to versions** and have **no deterministic runner that wires their output back to the agent** — the agent must shell out manually and re-parse free-form output each run. `ruff` is a dev dependency in `pyproject.toml` (`ruff>=0.11.13`) but is **absent from the container image**; `pytest` is neither pinned nor present in the image. Result: non-reproducible scans and a CI/sandbox skew.
2. **Import side effects block unit testing.** `strix/interface/utils.py` does an eager `import docker` / `from docker.errors import ...` at module top (lines 17–18). Because importing the module pulls in the Docker SDK (and, transitively, a live daemon expectation), the existing regression test `tests/test_core_paths.py` cannot simply `from strix.interface.utils import validate_repo_url`. It is forced to load the module **by file path** via `importlib.util.spec_from_file_location` (lines 14–23) just to reach pure functions like `validate_repo_url` and `clone_repository`. This is a smell that will repeat at every dangerous boundary we add (net, oob, identity).
3. **Outbound-trust hardening is only half-landed.** Branch `fix/run-path-and-clone-hardening` added `validate_repo_url` (scheme/transport allowlist) and `validate_run_name` (path-traversal). But the SSRF surface is broader: `_is_localhost_host` (utils.py:1215) only recognizes loopback + `0.0.0.0` + `::1`; `rewrite_localhost_targets` (utils.py:1233) rewrites only those. There is **no URL normalization**, **no redirect-chain revalidation** (`_is_http_git_repo` at utils.py:1051 follows redirects via `urlopen` with no re-check), **no handling of alternate IP notations** (decimal/octal/hex IPv4, IPv4-mapped IPv6, `[::ffff:a9fe:a9fe]`), and **no internal-CIDR / cloud-metadata** corpus (`169.254.169.254`, `100.64.0.0/10`, RFC-1918, link-local). This is the exact surface advice #6 flags and Phase 2 (OOB oracle) will rely on.
4. **Severity is not impact-gated.** `strix/tools/reporting/tool.py` derives severity **purely from a CVSS breakdown** (`_calculate_cvss`, line 122; severity flows from `c.severities()[0]`). `strix/report/state.py::add_vulnerability_report` stores whatever severity it is handed. Nothing enforces roadmap **principle 3** ("gate severity on demonstrated impact") — a finding with a high CVSS vector but **no evidence** (no diff, no callback, no reachability path) is reported at full severity, which is precisely the scanner-like noise the program exists to kill.

**Intent:** make the foundation reproducible, testable, hardened, and impact-honest so Phases 1–5 build on solid ground.

---

## 2. Who benefits & how

- **The strix agent** — gets a deterministic, version-pinned scanner surface with structured (parseable) results wired straight into its tool context, instead of re-shelling and re-parsing free text.
- **The bounty operator / human reviewer** — sees fewer over-rated findings because severity is gated on evidence; trusts that an internal-target SSRF can't slip through normalization gaps.
- **The strix dev team** — can unit-test dangerous-boundary modules in isolation (no Docker daemon, no network) and run the same `ruff`/`pytest` in CI and sandbox, closing the skew.
- **Every later phase** — Phase 2's OOB oracle reuses the hardened net layer and its target corpora; Phase 1/3/4 reuse the import-discipline pattern and the impact-gate.

---

## 3. Core functionality (scope)

### 3.1 Toolchain bundling & result wiring (advice #11)
- Pin `gitleaks`, `trufflehog`, `trivy`, `ruff`, `pytest` to explicit versions in the image build (`containers/Dockerfile`) and, where they are Python tools, in `pyproject.toml`.
- Add a **build-time self-check** that fails the image build if any of the five is missing or not on `PATH` for the `pentester` user.
- Provide a **deterministic scanner-runner seam** (a tool the agent invokes) that executes a named scanner against a target/workspace and returns **structured results** (tool, version, target, findings list, raw-output pointer) — not free-form stdout the model must re-parse.
- Surface scanner availability/version to the agent so it never guesses whether a tool exists.

### 3.2 Import-side-effect reduction (advice #12)
- Make `strix/interface/utils.py` (and the new net module) importable **without** importing `docker` or contacting a daemon: defer/relocate Docker-dependent code so pure validators (`validate_repo_url`, `validate_run_name`, target parsing, URL normalization, net validators) import cleanly.
- Goal contract: `from strix.interface.utils import validate_repo_url` (and the new net validators) succeeds with **no Docker SDK import** and **no network**. The existing file-path-loading hack in `tests/test_core_paths.py` becomes unnecessary (kept working for back-compat, but new tests use direct imports).

### 3.3 Outbound-trust hardening (advice #6, partial — black-box portion only)
A new cohesive `strix/core/net/` module (per roadmap "new `strix/core/net/`") providing:
- **URL normalization** — canonicalize scheme/host/port/path; lowercase host; strip default ports; resolve `userinfo`; **idempotent** (`normalize(normalize(u)) == normalize(u)`).
- **Alternate IP-notation decoding** — decimal (`2130706433`), octal (`0177.0.0.1`), hex (`0x7f.0.0.1`), zero-compressed and IPv4-mapped IPv6 (`::ffff:127.0.0.1`), so they classify the same as their canonical form.
- **Internal-target rejection** — a classifier that flags loopback, RFC-1918, link-local (`169.254.0.0/16`), CGNAT (`100.64.0.0/10`), ULA (`fc00::/7`), and **cloud-metadata** endpoints (`169.254.169.254`, `fd00:ec2::254`, GCP/Azure metadata hosts) across **all** notations from the previous bullet.
- **Redirect-chain revalidation** — when following redirects (extends `_is_http_git_repo`'s `urlopen` path), **every hop** is re-normalized and re-classified; a redirect to an internal target is rejected even if the original target was external.
- **Curated target corpora** — internal-CIDR and cloud-metadata payload fixtures (canonical + alternate notations) used by both the validator and the PBT suite.
- **OOB-confirmation hook seam** — a thin, no-op-by-default interface point where Phase 2's OOB oracle will plug in to confirm a suspected SSRF via callback. Phase 0 defines the seam and a null implementation only; **the real oracle is Phase 2**.

### 3.4 Impact-gated severity policy (advice #10, principle 3)
- Make the impact gate **explicit** in the report layer (`strix/report/state.py` / reporting tool path): a finding carries an **evidence class** (one of: `diff` (P2), `callback` (P3), `reachability` (P4), or `none`), and severity is **capped / down-graded when evidence class is `none`** (e.g., to `info`/unconfirmed) rather than reported at full CVSS-derived severity.
- The policy must be **inspectable** (glass-box): the gate decision and the evidence class are recorded on the report record.
- Phase 0 ships the **policy and the `none` path**; the concrete evidence producers (diff/callback/reachability) arrive in Phases 1–3 — Phase 0 only needs the gate to recognize and honor them when present.

---

## 4. User stories

1. **As the strix agent**, I want every required scanner pinned and present in my sandbox with structured output, so that I get reproducible results without re-parsing free-form stdout or guessing whether a tool exists.
2. **As a strix developer**, I want to unit-test `validate_repo_url` and the net validators with a plain `import`, so that I can test dangerous-boundary logic in isolation without a Docker daemon or network.
3. **As a strix developer**, I want the SSRF/outbound validator to reject internal and cloud-metadata targets across normalized and alternate notations — including across redirect hops — so that the agent cannot be steered into the host's internal network or metadata service.
4. **As a bounty operator**, I want findings without demonstrated impact down-graded automatically, so that my attention lands on evidence-backed findings instead of CVSS-on-paper noise.
5. **As a Phase 2 implementer**, I want a defined OOB-confirmation hook in the net layer, so that I can wire the real OOB oracle in without re-plumbing the SSRF path.

---

## 5. Constraints

- **WHAT not HOW** in `spec.md`; detailed analysis stays here.
- **No new primitive.** Phase 0 introduces no P1–P4; it is an enabler. The OOB seam is a *seam*, not the P3 oracle.
- **Back-compat:** existing CLI behavior, `clone_repository`, `rewrite_localhost_targets`, and `tests/test_core_paths.py` must keep passing.
- **Component cohesion:** backend modules single-responsibility; `strix/core/net/` stays cohesive; no module bloat.
- **Estimates in iterations, never hours/days.**
- **Test budget:** 16–34 focused tests total; security-critical net + impact-gate components additionally get Tier-2 PBT.
- **Build determinism:** pinned tool versions; image self-check must be hermetic (no flaky network asserts beyond install).
- **Don't over-reach into later phases:** no real OOB oracle, no diff/reachability producers here.

---

## 6. Reusable strix code identified (reuse before build)

Verified in-repo anchors (cited by file + symbol):

- **`strix/interface/utils.py`**
  - `validate_repo_url` (line 1259) and `validate_run_name` (imported from `strix.core.paths`) — the landed hardening to *extend*, not replace.
  - `_is_localhost_host` (1215), `rewrite_localhost_targets` (1233) — current internal-host logic to generalize into `strix/core/net/`.
  - `_is_http_git_repo` (1051) — the `urlopen` redirect-following path to wrap with revalidation.
  - `infer_target_type` (1063), `urlparse` usage — target parsing the normalizer integrates with.
  - Eager `import docker` / `from docker.errors` (17–18), `check_docker_connection` (1366), `image_exists` (1391) — the Docker-coupled code to relocate/defer for import-side-effect reduction.
- **`tests/test_core_paths.py`** — the unittest + `importlib.spec_from_file_location` pattern (lines 14–23) to mirror for new tests; the existence of the file-path hack is the motivating evidence for advice #12.
- **`containers/Dockerfile`** — existing (unpinned) `trufflehog`/`gitleaks`/`trivy` installs (134–150), `pipx`/`npm`/`go install` patterns, `pentester` user + `PATH` (167, 205) — extend for pinning + `ruff`/`pytest` + self-check.
- **`pyproject.toml`** — `ruff>=0.11.13` (line 53) and `[tool.ruff]` config (111+) — pin and align with image.
- **`strix/runtime/docker_client.py`** — `StrixDockerSandboxClient` sandbox lifecycle — where the bundled toolchain is consumed; reference for where the scanner-runner executes.
- **`strix/tools/`** — existing tool surface (`shell`, `reporting`, `proxy`, `web_search`, `notes`, `todo`, `thinking`, `finish`) and registration pattern — the deterministic scanner-runner registers here alongside `shell`/`reporting`.
- **`strix/tools/reporting/tool.py`** — `_calculate_cvss` (122), `_do_create` (154), `add_vulnerability_report` call (261) — the path the impact-gate hooks into.
- **`strix/report/state.py`** — `add_vulnerability_report` (139), the report record dict (162), `vulnerability_reports`, severity normalization (`severity.lower().strip()`) — anchor for impact-gating + evidence-class field.
- **`strix/core/paths.py`** — `validate_run_name`, `run_dir_for`, `RUNS_DIR_NAME` — pure-helper pattern to mirror for net validators.

---

## 7. Risks & assumptions

| # | Risk / assumption | Mitigation |
|---|---|---|
| R1 | Pinning tool versions in a Kali-rolling base may conflict with rolling packages. | Pin via direct release downloads (already the pattern for gitleaks/trivy), not apt where possible; self-check fails loud. |
| R2 | Relocating `import docker` could break callers relying on `utils.check_docker_connection`. | Keep public symbols; defer the import inside the function (lazy import) rather than moving the function. Back-compat test. |
| R3 | Over-aggressive internal-target rejection blocks legitimate external scans (false positives). | Corpus-driven tests assert external public targets pass; rejection list is explicit and reviewed. |
| R4 | Alternate-notation IP decoding is a classic bug farm (octal/overflow edge cases). | Tier-2 PBT: ∀ alternate notation, decoded address classifies identically to canonical; differential against `ipaddress`. |
| R5 | Impact-gate could hide real findings if evidence wiring lags (Phases 1–3 not built yet). | `none` path **down-grades, not drops**; finding stays visible (as unconfirmed) and is fully inspectable. |
| R6 | Redirect revalidation adds latency / could loop. | Hop cap + per-hop timeout; reuse existing `urlopen(timeout=10)` discipline. |
| A1 | Assumption: scanner-runner returns structured JSON the agent consumes; raw output is pointer-referenced, not inlined. | Confirmed feasible: tools already return dicts (see reporting tool). |
| A2 | Assumption: the OOB seam can be a null interface in Phase 0 with no behavioral cost. | Seam is a strategy object defaulting to "no confirmation available". |

---

## 8. Gate 1 pre-check (design-principle alignment)

- **Enhance human capability?** Yes — reproducible tools + impact-gating amplify the operator; nothing is automated away.
- **Support focus / avoid distraction?** Yes — impact-gating and tighter SSRF rejection cut noise.
- **Glass-box?** Yes — structured scanner results, recorded evidence class, inspectable gate decision, pinned versions.

Gate 1 pre-check: **PASS** (re-validated formally in `spec.md`).
