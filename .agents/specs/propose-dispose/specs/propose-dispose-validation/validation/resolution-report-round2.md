# Resolution Report — propose-dispose-validation (F-PD-B) — round 2

## Header

```
spec_id:        propose-dispose-validation
feature:        F-PD-B  (type: research, non-gating)
round:          2 (validation review + corpus expansion)
validator:      operator (pt-act / RA)
pm_dispatcher:  claude-sonnet-4-6 (Nyx / Eragon)
round_1_closed: 2026-07-24T11:01:57Z
round_2_closed: 2026-07-25T05:36:00Z
verdict:        APPROVED — cycle closed
push_commit:    36af62b (final paper + completion report update)
cosmetic_commit: 268b164 (no-op: paper footer test count check was false positive)
branch:         new
```

---

## §1 — Validator Verdict

> *"the paper is now publication-ready from a validation standpoint — artifact-consistent, all experiments live, no pilot labels, no stale numbers."*

Round 2 verdict: **APPROVED, cycle closed.**

All round-1 deficiencies resolved. The remaining gates (HOLD LINE, REPRODUCE.md, pre-registration lock, legal framing) are on the v1-release-checklist and are producer work, not validation work.

---

## §2 — Round 1 → Round 2 Delta

| Dimension | Round 1 | Round 2 |
|-----------|---------|---------|
| E1 | pilot (static proxy) ⚠️ | live ✅ — real haiku + Docker |
| E2 | b=10, p=0.0044 | **b=13, p=0.0009** ✅ independently re-verified |
| E3 | pilot (static proxy) ⚠️ | live ✅ — honest null (Prec_gate=1.0 all conditions) |
| E4 | pilot (static proxy) ⚠️ | live ✅ — 0/20 strix flips, 2/20 M4 flips |
| Corpus real CVEs | 2/10 | **5/13** ✅ |
| Paper stale values | present | all corrected ✅ (automated sweep confirmed) |
| Tests | 568 pass | **577 pass** ✅ |

### New real CVEs added (round 2)

| Pair ID | CVE | GHSA | Primitive | Fix size |
|---------|-----|------|-----------|----------|
| `openwebui-bfla-arena-model` | CVE-2026-59225 | GHSA-m3qf-58wf-w979 | BFLA | 6 lines |
| `openwebui-bfla-kb-upload` | CVE-2026-59217 | GHSA-7r7x-gjvr-448g | BFLA | +32/-12 lines |
| `openwebui-path-traversal-proxy` | CVE-2026-59221 | GHSA-frvj-c5qp-xj4w | Path traversal | 3 lines |

All sourced from public GitHub Security Advisories (open-webui, merged June 2026). All self-contained FastAPI fixtures with VULN_MODE switch. All harness flips smoke-tested independently (vuln=200, patch=400/403).

### Cosmetic issue (false positive)

> *"paper footer doesn't reference test count at all — the check was a false positive. no fix needed."*

- Commit `268b164` — no-op. No paper edit required.

---

## §3 — Standing Deviations (post-round-2)

### DEV-6 — E2 pre-registration not locked ⚠️ (open — operator action required)

- **Status:** unchanged from round 1
- **Required action:** Operator sets `Status: LOCKED` in `.agents/specs/propose-dispose/specs/propose-dispose-validation/planning/E2-preregistration.md` before any future confirmatory E2 claim
- **Impact:** The n=13 E2 result (`b=13, c=0, p≈0.0009`) stands as a strong exploratory finding. It cannot be claimed as pre-registered until the lock is set. Any future E2 extension (new corpus, new model) must be pre-registered first.
- **Blocking production?** No — paper is publication-ready. DEV-6 is a research-integrity gate for future extensions, not the current result.

### DEV-7 — path_traversal_proxy harness probe edge case 📋 (backlog, non-blocking)

- **Pair:** `openwebui-path-traversal-proxy` (CVE-2026-59221)
- **Observation:** In the live E2 run, `pd_harness_verdict="unconfirmed"` — the HTTP harness probe returned 403 on both vuln and patched containers (Starlette/FastAPI URL routing decoded the double-encoded path before the app handler received it, making the vuln and patched responses identical at the HTTP layer).
- **Standalone smoke test:** vuln=200, patch=403 — the fixture logic is correct when probed directly.
- **Root cause:** FastAPI's Starlette router normalizes percent-encoded path segments before dispatch. The double-encoded payload `%252e%252e%252f` → Starlette decodes `%25` → `%2e%2e%2f` → decoded again to `../`. The `sanitize_proxy_path` function receives an already-decoded path and the traversal is caught by the `/static/` prefix guard on both vuln and patched — making them indistinguishable at HTTP response level.
- **Backlog item:** `PD-VAL-7` — replace double-encoded path probe with a single-encoded traversal that Starlette passes through, or restructure the fixture to apply the decode logic before Starlette routing (e.g., via raw ASGI middleware).
- **Impact on paper:** FN-arm c=1 (honest). The paper correctly notes the path_traversal edge case. Result is not invalidated; H2b tie (p=1.0) holds regardless.

---

## §4 — Final Experimental Summary (n=13, all experiments live)

### E2 Primary Result (H2a) — McNemar FP-arm

| Metric | Value |
|--------|-------|
| n (small-gap pairs) | 13 |
| b (strix correct, M4 wrong on patched) | 13 |
| c (M4 correct, strix wrong on patched) | 0 |
| χ² (continuity-corrected) | 11.077 |
| p (two-sided McNemar) | **≈ 0.0009** |
| H2a | **CONFIRMED** |

### E2 FN-arm (H2b)

| Metric | Value |
|--------|-------|
| b | 0 |
| c | 1 (path_traversal_proxy, DEV-7) |
| p | 1.0 |
| H2b | honest tie — strix inherits proposer recall ceiling |

### E1 — Tradeoff Curve (H1)

| Aggressiveness | n_pairs | R_prop | Prec_gate | m4_recall |
|----------------|---------|--------|-----------|-----------|
| conservative | 13 | 0.462 | 1.000 | 0.308 |
| moderate | 13 | 0.923 | 1.000 | 0.769 |
| aggressive | 13 | 1.000 | 1.000 | 1.000 |

H1 **CONFIRMED** — Prec_gate=1.000 at all levels; SS precision collapses as recall is pushed.

### E3 — Intervention Ablation (H3)

| Condition | R_prop | Prec_gate |
|-----------|--------|-----------|
| full | 1.000 | 1.000 |
| no_control | 1.000 | 1.000 |
| no_knowledge | 1.000 | 1.000 |
| no_checklist | 1.000 | 1.000 |

H3 **honest null** — haiku proposes on all 13 pairs regardless of surface context. Harness gate, not proposer context, carries the discriminating burden. Prec_gate=1.000 structural result is independent of corpus size.

### E4 — Perturbation Invariance (H4)

| Metric | Value |
|--------|-------|
| Seed pairs | 5 |
| Perturbations per pair | 5 (baseline, rephrase_endpoint, add_noise_params, reword_cve, minimal_surface) |
| Total observations | 5 × 5 = 25 (5 seeds × 5 perturbations × strix + M4) |
| strix flips vs baseline | 0 / 20 |
| M4 flips vs baseline | 2 / 20 |
| H4 | **CONFIRMED** |

---

## §5 — Artifact Registry (final, round 2)

| Artifact | Path | Commit | Status |
|----------|------|--------|--------|
| Paper v1.0 (final) | `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` | 36af62b | ✅ publication-ready |
| Live E2 results (n=13) | `artifacts/live_experiment_results.json` | 31ef9dc | ✅ |
| Live E1 results (n=13) | `artifacts/e1_live.{json,csv}` | 31ef9dc | ✅ |
| Live E3 results (n=13) | `artifacts/e3_live.{json,csv}` | 31ef9dc | ✅ |
| Live E4 results (5 seeds) | `artifacts/e4_live.{json,csv}` | 31ef9dc | ✅ |
| Combined results | `artifacts/live_e1e3e4_results.json` | 31ef9dc | ✅ |
| Corpus registry (n=13) | `strix/research/corpus.py` | 31ef9dc | ✅ |
| Fixture: bfla_arena_model | `benchmarks/bv2p/bfla_arena_model/` | 31ef9dc | ✅ |
| Fixture: bfla_kb_upload | `benchmarks/bv2p/bfla_kb_upload/` | 31ef9dc | ✅ |
| Fixture: path_traversal_proxy | `benchmarks/bv2p/path_traversal_proxy/` | 31ef9dc | ✅ |
| Corpus tests (n=36) | `tests/test_bv2p_corpus.py` | 31ef9dc | ✅ (577 pass total) |
| Completion report | `validation/completion-report.md` | 36af62b | ✅ |
| This resolution report | `validation/resolution-report-round2.md` | — | ✅ |

---

## §6 — v1-Release-Checklist Handoff (producer work)

The following gates are **not** validation gates — they are release-checklist items for the producer:

- [ ] **HOLD LINE** — freeze paper after this commit; no further empirical edits without a new pre-registered round
- [ ] **REPRODUCE.md** — write minimal reproduction instructions (Docker + haiku key + `run_live_experiments.py`)
- [ ] **Pre-registration lock** — set `Status: LOCKED` in `E2-preregistration.md` (DEV-6)
- [ ] **Legal framing** — confirm open-webui / flowise fixture licensing acceptable for publication
- [ ] **No-imported-magnitudes audit** — final check: no FPR/ρ/F1 magnitudes from prior art used as coordinates (task 5.9)
- [ ] **DEV-7 backlog** — fix path_traversal_proxy harness probe for robust double-encode handling (PD-VAL-7)

---

*Resolution report filed by Nyx/Eragon (PM dispatcher) — 2026-07-25T05:36:00Z*
