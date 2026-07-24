# Dependency Hardening Brief — clear the Dependabot advisories

**From:** PM-Auditor-Validator
**For:** Hermes (coder)
**When:** **after** the Phase-5 integration closure is merged to `main` — not before (avoids the Phase-5 branch fighting a moving lockfile).
**Scope:** dependency vulnerabilities only (the Dependabot set). Secrets/filesystem scans are a separate pass.
**Origin:** Dependabot flagged 38 advisories on `ca4fd09`. Independently reproduced via `pip-audit` against the same lockfile: **43 raw / ~38 deduped advisories across 10 packages, every one with a fix version available.** Pure staleness, not a code defect.

---

## The inventory (current → fix), with batch/isolate decision

| Package | Pinned | Bump to ≥ | Risk | Lane |
|---|---|---|---|---|
| aiohttp | 3.13.5 | 3.14.1 | minor — 11 CVEs, outbound HTTP path | **batch** |
| pyjwt | 2.12.1 | 2.13.0 | patch — ~5 advisories, token handling | **batch** |
| python-multipart | 0.0.20 | 0.0.31 | patch — 6 CVEs, form/upload parsing | **batch** |
| requests | 2.32.5 | 2.33.0 | patch | **batch** |
| urllib3 | 2.6.3 | 2.7.0 | patch | **batch** |
| idna | 3.11 | 3.15 | patch, transitive | **batch** |
| pygments | 2.19.2 | 2.20.0 | patch, TUI render | **batch** |
| python-dotenv | 1.0.1 | 1.2.2 | patch, config load | **batch** |
| **starlette** | 0.50.0 | 1.3.1 | **MAJOR (0.x→1.x)** — web/proxy parsing | **isolate** |
| **cryptography** | 43.0.3 | 48.0.1 | **multi-major (43→48)** — crypto/replay | **isolate** |

---

## Locked approach (read before touching anything)

1. **Do it via `uv lock --upgrade-package`, not by merging the open Dependabot PRs.** One controlled lockfile change per lane is cleaner and auditable; the Dependabot PRs (aiohttp, cryptography, python-multipart, starlette) get closed as superseded afterward.
2. **The full gate is the acceptance test for every bump.** A dependency bump that breaks a test or a type/lint/bandit check is a failed bump — fix or pin back, never merge red.
3. **Batch the 8 safe ones; isolate the 2 majors on their own branches.** Never blind-bump a major.
4. **Re-audit after each lane** to prove the advisories actually cleared.

---

## Lane 1 — batch the 8 safe bumps

```bash
git checkout main && git pull            # AFTER Phase 5 is merged
git checkout -b dep-hardening-batch
uv lock --upgrade-package aiohttp --upgrade-package pyjwt \
        --upgrade-package python-multipart --upgrade-package requests \
        --upgrade-package urllib3 --upgrade-package idna \
        --upgrade-package pygments --upgrade-package python-dotenv
uv sync --group dev
# FULL GATE (all green together):
uv run ruff check . && uv run ruff format --check . \
  && uv run mypy strix/ && uv run pyright strix/ \
  && uv run bandit -r strix/ -c pyproject.toml \
  && uv run pytest tests/ -q
# confirm the advisories cleared:
uv run --with pip-audit pip-audit --desc off
```
Green → commit, push, open PR, close the superseded Dependabot PRs it covers.

## Lane 2 — starlette (MAJOR, isolate)

```bash
git checkout main && git checkout -b dep-starlette
uv tree --invert --package starlette     # WHAT pulls in starlette + any version constraint?
```
- **Investigate first.** Starlette 1.0 is a major release; whatever depends on it may pin a `<1.0` range. If a parent constrains it, you cannot land 1.3.1 by bumping starlette alone — you must bump the parent too, or take the highest fixed version the parent allows. Do **not** force-override a constraint.
- Bump (`uv lock --upgrade-package starlette`, plus the parent if required) → `uv sync` → **full gate** → then **exercise the web/proxy request-parsing paths specifically** (the OOB listener / any server component / multipart handling), since that's where a starlette major breaks. Fix breakage, re-run, re-audit.
- If starlette 1.x is genuinely unreachable given the dependency tree, document that in the PR and take the highest reachable fixed version; note any residual advisory as accepted-with-reason.

## Lane 3 — cryptography (multi-major, isolate)

```bash
git checkout main && git checkout -b dep-cryptography
uv lock --upgrade-package cryptography     # → 48.x
uv sync --group dev
# full gate, then exercise crypto/identity/replay paths
uv run --with pip-audit pip-audit --desc off
```
- 43→48 crosses several majors; cryptography is usually backward-compatible but verify any direct API use (signing, cert handling, the identity/redaction paths). Gate + targeted exercise, fix, validate.

---

## Validation discipline
- Every lane: `ruff` + `ruff format --check` + `mypy strix/` + `pyright strix/` + `bandit -r strix/ -c pyproject.toml` + full `pytest tests/` — all green **together** before merge.
- The two majors additionally require **exercising the affected runtime paths**, not just a green unit suite — a passing test suite doesn't prove starlette 1.x didn't change request-parsing behavior strix relies on.
- After all three lanes, a final `pip-audit` on `main` should show the advisory count at zero (or only items explicitly accepted-with-reason in a PR note).

## Hygiene
- Explicit `git add`; never `-A`. Never `git add` `.agents/` or `manifest.yml`.
- Close the superseded Dependabot PRs once the equivalent bump merges.
- One PR per lane so a regression can be reverted in isolation.

---

## Coder prompt (relay to Hermes, after Phase 5 merges)

```text
Clear the Dependabot dependency advisories on main (43 raw / ~38 deduped across 10 packages, all with
fix versions). Do it via `uv lock --upgrade-package`, not by merging the Dependabot PRs. The full gate
(ruff + ruff format --check + mypy strix/ + pyright strix/ + bandit -r strix/ -c pyproject.toml + full
pytest tests/) is the acceptance test for every bump — never merge red.

LANE 1 (batch, safe): aiohttp>=3.14.1, pyjwt>=2.13.0, python-multipart>=0.0.31, requests>=2.33.0,
urllib3>=2.7.0, idna>=3.15, pygments>=2.20.0, python-dotenv>=1.2.2. One branch, one lock upgrade,
gate, pip-audit to confirm cleared, PR.

LANE 2 (starlette, MAJOR — isolate): starlette 0.50 -> 1.3.1 is a 0.x->1.x major. FIRST run
`uv tree --invert --package starlette` to see what depends on it and whether that constrains the bump;
if a parent pins <1.0 you must bump the parent too or take the highest reachable fixed version — do not
force-override. Bump, gate, then EXERCISE the web/proxy/multipart request-parsing paths (that's where a
starlette major breaks). Fix breakage, re-audit, PR. Document any residual advisory as accepted-with-reason.

LANE 3 (cryptography, multi-major — isolate): 43 -> 48. Bump, gate, exercise the crypto/identity/replay
paths, re-audit, PR.

Per lane: explicit git add (never -A; never add .agents/ or manifest.yml); one PR each; close the
superseded Dependabot PRs as you go. A green unit suite is necessary but NOT sufficient for the two
majors — exercise the affected runtime paths. Final state: pip-audit on main shows zero (or only
documented accepted-risk).
```
