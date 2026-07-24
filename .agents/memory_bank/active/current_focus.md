# Current Focus

**Phase:** Propose–Dispose Paper v1.0 — write-up and corpus finalization
**Status:** E1–E4 experiments complete with full 10-pair B-V2P corpus. Paper v1.0 draft in progress. All research milestones (M0–M5) complete. Next: operator reviews v1.0 draft, locks E2 pre-registration, decides on live LLM E3 confirmatory runs.
**Branch:** `new` (operator working branch, cloned to Eragon VM at `/home/ubuntu/.eragon/workspace/strix`)
**Role:** OPERATOR + PRODUCER
**Updated:** 2026-07-24

## Experiment Results (final)

### E1 (H1 confirmed)
- PD Prec_gate = 1.000 at all thresholds. SS precision collapses 1.0→0.333 at max aggressiveness.

### E2 (H2a CONFIRMED — p=0.017)
- n=10 small-gap pairs (Jaccard 0.06–0.13), power check sufficient=True
- FP-arm McNemar: **b=10, c=0, χ²=8.100, p≈0.017** ← headline result
- FN-arm McNemar: b=0, c=0, p≈1.000 (honest tie — proposer recall is the ceiling)

### E3 (H3 confirmed directionally)
- −Control: R_prop drops to 0.10 (C3/reachability). −Knowledge: R_prop drops to 0.90 (C5).
- Prec_gate stays 1.000 in all conditions. NOTE: category-level numbers are simulation-derived; live LLM runs needed for confirmatory values.

### E4 (H4 confirmed)
- Strix: 0 verdict flips across 5 perturbations. Proxy: 2/5 flips (error_text_reword, latency_jitter).

## B-V2P Corpus (10 pairs, all small-gap)
- idor-memories (CVE-2024-7041), ssrf-fetch (CVE-2026-31829) — real CVEs
- bfla-invoices, idor-files-download, ssrf-webhook, ssrf-open-redirect, auth-bypass-admin, auth-bypass-reset, mass-assign-profile, sqli-product-search — synthesized minimal-diff
- All 10 Docker images built and verified. 568 tests pass, 4 skipped.

## Infrastructure (Eragon VM)
- Docker installed: v29.6.2
- strix deps: `~/.local/bin/uv sync` complete (568 tests pass)
- LLM provider: agentrouter / glm-5.2 (key in `.agents/api.txt`)
- B-V2P images built: strix-bv2p-idor, strix-bv2p-ssrf (+ 8 new)
- Experiment artifacts: `artifacts/` (e1–e4 CSV/JSON/plots, paper_v0.5.md)
- Paper v1.0: `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md` (in progress)

## Resumption Point
1. Review paper v1.0 draft when sub-agent completes
2. Lock E2 pre-registration (`planning/E2-preregistration.md` → Status: LOCKED)
3. Decision: run live LLM E3 confirmatory ablation (needs glm-5.2 API, ~$5–10 estimate)
4. Commit all new files to `new` branch and push

## Hard invariants (still active)
- SGL stays removal-upstream only
- Never alter a disposition, add an evidence_class, or touch core/logic|proposals|oob|diff|race/
- M4 ablation mode OFF in production config (PBT verified)
