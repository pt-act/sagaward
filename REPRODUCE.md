# REPRODUCE.md — Strix Propose–Dispose Validation

Minimal reproduction guide for E1–E4 experiments from the paper
**"Propose–Dispose: Gap-Dictation in LLM-Assisted Vulnerability Triage"**.

All experiments use `anthropic/claude-haiku-4-5` as the external producer via OpenRouter,
and real Docker containers as the target fixtures. No simulation, no static proxy.

---

## Prerequisites

- Python ≥ 3.12 (tested on CPython 3.14.6)
- [`uv`](https://docs.astral.sh/uv/) — `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker ≥ 24 (tested on 29.6.2) — `sudo` required unless user is in `docker` group
- An [OpenRouter](https://openrouter.ai) API key with access to `anthropic/claude-haiku-4-5`

---

## 1. Clone and set up

```bash
git clone https://github.com/pt-act/strix.git
cd strix
git checkout new
uv sync
```

---

## 2. Build Docker fixtures

All 13 B-V2P fixture images must be built before running experiments.

```bash
# From repo root — run all builds
for fixture in \
  idor_memories bfla_invoices idor_files \
  ssrf_webhook ssrf_redirect ssrf_fetch \
  auth_bypass_admin auth_bypass_reset \
  mass_assign_profile sqli_search \
  bfla_arena_model bfla_kb_upload path_traversal_proxy; do
  echo "building strix-bv2p-${fixture}..."
  sudo docker build -t strix-bv2p-${fixture} benchmarks/bv2p/${fixture}/
done

# ssrf_webhook and ssrf_redirect require repo-root build context:
sudo docker build -f benchmarks/bv2p/ssrf_webhook/Dockerfile -t strix-bv2p-ssrf_webhook .
sudo docker build -f benchmarks/bv2p/ssrf_redirect/Dockerfile -t strix-bv2p-ssrf_redirect .
```

Verify all 13 images exist:
```bash
sudo docker images | grep strix-bv2p
```

---

## 3. Run E2 (primary experiment)

E2 is the primary McNemar experiment. It runs all 13 pairs twice each (PD mode + M4 baseline),
then computes the FP-arm and FN-arm McNemar statistics.

```bash
export OPENROUTER_API_KEY="<your-openrouter-key>"
export STRIX_LLM="anthropic/claude-haiku-4-5"
export LLM_API_BASE="https://openrouter.ai/api/v1"

uv run python artifacts/run_live_experiments.py
```

Expected output:
```
FP-arm (H2a): b=13, c=0, χ²=11.077, p=0.0009 → H2a=CONFIRMED
FN-arm (H2b): b=0, c=1, χ²=0.0, p=1.0
```

Results saved to: `artifacts/live_experiment_results.json`

---

## 4. Run E1, E3, E4

E1 (tradeoff curve), E3 (ablation), and E4 (perturbation invariance) are run together:

```bash
export OPENROUTER_API_KEY="<your-openrouter-key>"
export STRIX_LLM="anthropic/claude-haiku-4-5"
export LLM_API_BASE="https://openrouter.ai/api/v1"

uv run python artifacts/run_live_e1e3e4.py
```

Expected output summary:
```
E1 H1: confirmed=True | Prec_gate min=1.0
E3 H3: directional=True | Full R_prop=1.0
E4 H4: confirmed=True | strix_flips=0 m4_flips=2
```

Results saved to:
- `artifacts/e1_live.{json,csv}`
- `artifacts/e3_live.{json,csv}`
- `artifacts/e4_live.{json,csv}`
- `artifacts/live_e1e3e4_results.json`

---

## 5. Run tests

```bash
uv run pytest tests/ -q
# Expected: 577 passed, 4 skipped, 0 failures
```

---

## 6. Corpus

The B-V2P corpus is defined in `strix/research/corpus.py`. All 13 pairs:

| Pair ID | CVE | Type | Harness |
|---------|-----|------|---------|
| openwebui-idor-memories | CVE-2024-7041 | IDOR (real) | P2 diff |
| flowise-ssrf-http-node | CVE-2026-31829 | SSRF (real) | P3 callback |
| openwebui-bfla-arena-model | CVE-2026-59225 | BFLA (real) | P2 diff |
| openwebui-bfla-kb-upload | CVE-2026-59217 | BFLA (real) | P2 diff |
| openwebui-path-traversal-proxy | CVE-2026-59221 | Path traversal (real) | P2 diff |
| bfla-invoices | synthetic | BFLA | P2 diff |
| idor-files-download | synthetic | IDOR | P2 diff |
| ssrf-webhook-registration | synthetic | SSRF | P3 callback |
| ssrf-open-redirect | synthetic | SSRF | P0 reachability |
| auth-bypass-admin-panel | synthetic | Auth bypass | P2 diff |
| auth-bypass-password-reset | synthetic | Auth bypass | P2 diff |
| mass-assign-profile | synthetic | Mass assignment | P2 diff |
| sqli-product-search | synthetic | SQLi | P2 diff |

---

## 7. Known edge case

`openwebui-path-traversal-proxy` (CVE-2026-59221): the live E2 harness probe returns
`unconfirmed` on both containers because FastAPI/Starlette URL routing decodes
percent-encoded path segments before the app handler receives them. The fixture logic
is correct when probed directly (smoke test: vuln=200, patch=403). This is tracked as
DEV-7 / PD-VAL-7 (backlog, non-blocking). It contributes c=1 to the FN-arm, which
remains at p=1.0 (tied).

---

## 8. Paper

Main paper: `.agents/specs/propose-dispose/paper/propose-dispose-paper-v1.0.md`

Pre-registration: `.agents/specs/propose-dispose/specs/propose-dispose-validation/planning/E2-preregistration.md`
(Status: LOCKED at commit `268b164` — any future confirmatory E2 round requires a new pre-registration)

---

*Frozen at commit `268b164` on branch `new`. Producer: anthropic/claude-haiku-4-5 via openrouter.ai.*
