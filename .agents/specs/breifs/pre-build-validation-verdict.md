# Pre-Build Validation Verdict — strix bounty-grade engine

> PM/Validator checkpoint before docker build + empirical data gathering (E1–E4).
> Validator: `opus-4.8-pm-auditor` · Method: pm-auditor v2.1 (adversarial semantics) · Branch under test: `propose-dispose-validation @ a5b800c` · Date: 2026-06-18

## Header

- spec_under_review: `propose-dispose-validation` (Spec B, `type: research`, NON-gating) + a v2.1 adversarial re-verification of the precision-owning components inherited from phases 1–5 / Spec A.
- validator: `opus-4.8-pm-auditor`
- validator_distinct_from_producer: **false** — operator-approved same-model override (ARCH #6/#7). Verdict is **method-carried**: every finding cites a traced decision branch (file:line), a constructed true-negative case, and a reproduced command — not lineage.
- ref_commit: `a5b800c` (branch `propose-dispose-validation`; carries phases 0–5 + correctness-fix-pass + Spec A instrumentation + Spec B M1/M2/M4 + Step-0 hook + harness wiring). `main @ e4897ce` carries only the PR #16 duplicate of the instrumentation; the branch is the complete, buildable artifact.

## Decision

**GO for docker build + empirical data gathering — CONDITIONAL.**

The software and the locus-1 safety guarantees that gate the build are validated and reproducible. The remaining conditions below are research-validity and test-hygiene items, none of which block the build or the live runs; one (E2 pre-registration LOCK) is a hard gate on the *paper*, not the build.

A terminal Locus-1 `approved` for Spec B is **not** issued here, and correctly so: Spec B is `in_progress`, has **no producer completion-report.md**, and its experiment criteria (E1–E4, the live M0 run) are `not_started` by design — they execute on the operator host *after* this build. This verdict approves the **build-gating subset** and the **inherited precision semantics**; terminal approval of Spec B awaits the post-experiment completion report.

---

## Part 1 — Headline: the v2.1 concern (direction-inversion) is closed

The reason this validation exists (per `PM/validation-upgrade-adversarial-semantics.md`): a BFLA/expired **direction-inversion** and an OOB **timestamp/dedup** bug previously passed a green Locus-1 validation because tests asserted the *implementation's* behavior, not the *security semantics*. I re-derived each precision-owning component from first principles, constructed the true-negative (secure) case myself, and traced the real decision branch.

| Component | Branch traced | Fires on vuln? | Silent on secure case? | True-negative test asserts semantics? | Finding |
|---|---|---|---|---|---|
| Differential — **IDOR** | `core/diff/engine.py:167-189` | yes (same body, both 2xx) | yes (different bodies → no fire) | `test_idor_detection`, `test_diff_normalization_stability` | **CONFIRMED** |
| Differential — **expired-auth** | `engine.py:93-102,130-145` | yes (expired 2xx, baseline denied) | yes (expired denied → no fire) | `test_expired_denied_is_not_authorized` | **CONFIRMED** |
| Differential — **BFLA** | `engine.py:105-118,149-165` | fires on lower-succeeds + admin-denied | yes (admin 2xx, lower denied → no fire) | `test_correctly_gated_admin_endpoint_not_bfla` | **CONFIRMED (precision) + semantic caveat** (see F-2) |
| OOB correlator — unminted / foreign / expired / no-callback | `core/oob/correlator.py:34-66`; `tools/oob/tools.py:196,261` | yes | yes (quarantine/expire/unconfirmed) | mostly yes; **expired window untested** (F-1) | **CONFIRMED direction; major test gap** |
| OOB dedup (double-confirm) | `core/oob/registry.py:206-231`; `tools.py:263` | n/a | yes (2nd promote → no duplicate report) | `test_double_promote_dedups_to_one_report` | **CONFIRMED** |
| Race verdict / aggregator | `core/race/verdict.py:24-28`; `aggregator.py:176-185` | yes (commit_count>1) | yes (exactly 1 → "safe"; fail-safe to 1) | `test_single_commit_is_safe`, PBT `test_no_side_effect_on_safe_target` | **CONFIRMED** |
| Business-logic evidence gate | `core/logic/gate.py:18-21,39-60` | yes (impossible-state + typed artifact + reproduces) | yes (any guard fails → unconfirmed) | `test_rejects_model_allowed_state/no_artifact/non_reproducing` | **CONFIRMED** |

**No direction-inversion remains in any precision owner.** The catastrophic silent failure the upgrade was written to catch is resolved, and the true-negative (precision) direction is protected by semantic tests in every case except the OOB expiry window (F-1).

---

## Part 2 — Spec B build-gating deliverables (validated)

| Spec B item | Status | Evidence |
|---|---|---|
| **M4 single-stage ablation quarantine** (the one forbidden path) | **PASS** | Zero `import strix.research` outside `strix/research/`; `ablation/` imports nothing from `strix.report`; gated on exact sentinel `STRIX_RESEARCH_SINGLE_STAGE_ABLATION == "enable-single-stage-self-confirm-research-only"` (`single_stage.py:35-57`); all runners `RuntimeError` when unset; entrypoint is research-only `python -m strix.research.ablation`; `factory.py`/`tools/` reference it nowhere. Tests `test_disabled_by_default_and_runners_refuse`, `test_no_production_entry_module_imports_the_ablation`. |
| **Gate neutrality `C ⊆ P`** | **PASS** | `SingleStageVerdict` and `ProposalRecord` carry **no** `evidence_class`; `emit_harness_run` starts `none/unconfirmed` and can only promote to `confirmed` via `_EVIDENCE_TO_HARNESS` which excludes `"none"` (`funnel_emit.py:79-113`, `state.py:38-43`); `record_harness_run` mutates only `funnel_log`, never `vulnerability_reports` or the impact gate (`state.py:319-359`); `_link_disposer_verdict_to_funnel` demoted to link-only. The disposer is unmodified. |
| **M1 metrics (read-only)** | **PASS** | `metrics.py` reads a funnel log and computes via the pure `report.proposals.compute_*` fns; `__main__` is read-only over `funnel.json`; writes no report state. |
| **M2 B-V2P corpus** | **PASS** | IDOR `CVE-2024-7041` (synthesized one-line ownership check, `idor_memories/core.py:56-58`); SSRF `CVE-2026-31829` (patch reuses P0 `is_internal_target`, `ssrf_fetch/core.py:15,21-27`); both ship ground-truth `vuln_endpoint`, dockerized; recall-over-known + unknown-unknown caveat in `corpus.py:9-10`. Exploitability proven via the **real** P2 `diff()` and P0 classifier (`test_bv2p_corpus.py`). |
| **PR #17 conflict resolution** | **PASS** | Zero conflict markers in the tree; `test_boundary_is_structural` present; `state.py` resolved-vs-branch delta is the documented, safety-positive post-merge wiring patch (RESOLUTION.md §sequencing). |
| **Tier-1/Tier-2 gate (TG0–TG5 software)** | **PASS** | Targeted suites green: ablation 9, corpus 8, funnel-metrics 3, emit-hook 7, wrapper 8, proposals(assembler/funnel/disposer/integration) 28 = **63** passing; PBT 4.4 (production-off) + 4.5 (gate-neutrality) included. |

---

## Part 3 — Full gate reproduction (independent)

Run against `a5b800c` in this environment:

| Gate | Result | Note |
|---|---|---|
| `pytest tests/` (default order) | **370 passed, 4 skipped, 19 subtests** | Exactly matches the producer's claim. |
| `ruff check .` | **All checks passed** | clean |
| `ruff format --check .` | **214 files already formatted** | clean |
| `bandit -r strix/` | **clean** | warnings are acknowledged `nosec` markers, no failed tests |
| `mypy` (changed/precision surface, 35 files) | **Success: no issues found** | reproduces the mypy claim |
| `pyright strix/` | **could not reproduce "clean"** — 998 errors | **environmental, not a Spec B regression** — see F-3 |

---

## Issues Found

**F-1 · major · OOB expiry-window true-negative is untested.** `core/oob/correlator.py:57` (`hit.timestamp > mint.expires_at()` → `"expired"`) is the "timestamp" half of the named prior bug class and is currently **direction-correct**, but no test asserts that an expired callback yields `unconfirmed` / no report. A future flip (`>` → `>=`/`<`, or deleting the branch) would pass the entire green suite. *Remedy:* add a Tier-1 test — mint with a short `window_seconds`, deliver a hit past `expires_at`, assert `status=="expired"` at the correlator and `verdict=="unconfirmed"` with zero callback reports at the tool. Non-blocking for the run (direction is correct today); should land before the OOB/SSRF empirical numbers are treated as durable.

**F-2 · minor (semantic/naming) · BFLA predicate is privilege-inversion, not canonical BFLA.** `_is_bfla` (`engine.py:105-118`) fires only when the lower role succeeds **and admin is denied**. Canonical BFLA (lower-priv succeeds where admin *also* succeeds) is not flagged as BFLA — it is caught as **IDOR** when response bodies are identical, and missed when they differ. The test comment "true BFLA" (`test_diff_engine.py`) mislabels the inversion case. This is **precision-safe** (no false positive on a correctly-gated endpoint — confirmed by `test_correctly_gated_admin_endpoint_not_bfla`), and recall is the proposer's domain per the architecture; the M0 empirical seeds are IDOR/SSRF, not BFLA. *Remedy:* correct the comment/label; when BFLA B-V2P pairs are added to the corpus (tasks 2.1, deferred), account for this recall boundary in the paper rather than claiming canonical-BFLA detection.

**F-3 · major (claim-reproducibility, environmental) · "pyright clean" not reproducible here.** `pyright strix/` (the Makefile gate, `typeCheckingMode="strict"`) emitted 998 errors in this environment, but **only 8 fall inside Spec B's `strix/research/`** (benign `FunnelLog.load().list_records()` inference noise that mypy-strict accepts). The remaining ~990 are in pre-existing, already-approved phase 1–5 modules (inventory 119, logic 84, race 61, tui 56), and the per-root `executionEnvironments` exemptions in `pyproject.toml` did not apply as the producer's run implies — i.e. a **pyright version / config-resolution mismatch** (local pyright `1.1.408`), not a code regression and not a runtime risk. *Remedy:* pin the exact pyright version in the dev toolchain (and/or move pyright into pre-commit alongside mypy) so the "pyright clean" gate is reproducible by a stranger. The primary type gate (mypy-strict, in pre-commit) is clean.

**F-4 · minor (test hygiene) · gate is order-dependent.** The suite is green in default collection order but a non-default multi-file order surfaces a cross-file isolation leak — `test_race_harness.py::test_target_url_extraction` receives a `/api/users` URL leaked from another module; root cause is a module-level, never-restored mock at `tests/test_identity_replay.py:34` (`_caido_api.view_request = AsyncMock(...)`) and similar global mutations. Passes in isolation and in default order. *Remedy:* convert module-level mock mutations to fixtures/context managers with teardown before adopting `pytest-xdist` sharding or random ordering in CI.

---

## Conditions on the GO

1. **(Research-validity, hard gate on the paper — not the build):** the operator must set `planning/E2-preregistration.md` Status: **LOCKED** *before* any E2 outcome is observed (∀-invariant 6, pre-registration integrity). Building and running E1/E3/E4 may proceed; reading E2 results before the lock invalidates the McNemar-primary claim.
2. **(Recommended before durable OOB numbers):** land the F-1 expired-window true-negative test.
3. **(Operator/toolchain):** pin the pyright version (F-3) so the full static gate is reproducible; mypy-strict is already clean.
4. **(Before parallel CI):** fix the F-4 test-isolation leak.
5. **(Paper accuracy):** reflect the F-2 BFLA recall boundary; keep all magnitude claims self-measured (no imported FPR/ρ/F1), recall reported as recall-over-known.

Docker image build itself (full Kali toolchain image) is an operator-host step and was **not** reproduced here — consistent with the memory bank's own record ("full Kali image build not validated due to nuclei template timeout"). The bv2p fixture Dockerfiles are present and the corpus builds/imports cleanly.

---

## Verdict Rationale

The single highest-risk property for this engine — that a precision-owning detector silently fires on the *secure* case — was re-derived adversarially across the differential engine, OOB correlator, race verdict, and business-logic gate, and is **sound**: every component fires on the vulnerable case and stays silent on the secure case, with semantic true-negative tests present in all but the OOB expiry window (F-1). The Spec B build-gating software (M4 quarantine, gate-neutrality `C ⊆ P`, M1 metrics, M2 corpus) holds structurally and by test, and the functional gate (pytest/ruff/format/bandit/mypy) reproduces the producer's green claim. The only items that could not be reproduced or are unprotected are environmental or test-hygiene (F-3, F-4) or a deferred-corpus semantic note (F-2), none of which block building the image or starting empirical gathering. The one hard gate — locking E2 pre-registration before reading E2 — is a research-validity discipline on the paper, enforced by the operator at run time. **GO, conditional.**

---

## Session Manifest

- Skill: pm-auditor@2.1 (adversarial semantics)
- Interpreter: opus-4.8-pm-auditor
- Role: validator
- Spec: propose-dispose-validation (+ inherited precision owners, phases 1–5 / Spec A)
- Validation round: pre-build checkpoint (no producer completion-report for Spec B; experiments E1–E4 not_started by design)
- Branch/commit: propose-dispose-validation @ a5b800c
- Documents loaded: pm-auditor.md, VALIDATION_PROTOCOL.md, validation-upgrade-adversarial-semantics.md, MASTER_CONTEXT.md, manifest.yml, Spec B spec.md/tasks.md, RESOLUTION.md
- Criteria verified: 12 confirmed (7 precision-owning sub-decisions + 5 Spec B build-gating items) · 0 refuted · 0 unverifiable
- Reproduced commands: pytest (370/4/19), ruff check, ruff format --check, bandit, mypy (35 files), pyright strix/
- Decision: GO for docker build + empirical gathering — CONDITIONAL (no terminal Spec-B approval; awaits post-E1–E4 completion report)
- Issues: F-1 major (OOB expiry TN test gap) · F-2 minor (BFLA naming/recall) · F-3 major (pyright claim not reproducible — environmental) · F-4 minor (test-isolation order-dependence)
- Prior conflict: n/a (no producer-validator round on Spec B yet)
- Drift observed: no
- Escalations to operator: E2 pre-registration LOCK; pyright version pinning
