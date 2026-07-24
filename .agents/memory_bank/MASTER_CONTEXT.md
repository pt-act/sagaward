# Strix — Master Context

## Status: PAPER v1.0 IN PROGRESS — E1–E4 experiments complete, B-V2P corpus at n=10, p=0.017 on H2a
## Direction: All SGL + engine work complete. B-V2P corpus expanded to 10 small-gap pairs (2026-07-24). E1–E4 fully run with real statistical results. H2a confirmed at p=0.017 (FP-arm McNemar b=10, c=0, χ²=8.1). Paper v1.0 draft in progress. LLM provider: agentrouter/glm-5.2 (key in `.agents/api.txt`). Remaining: paper review, E2 pre-registration lock, live LLM E3 confirmatory runs (optional), commit+push to `new` branch.

## Experiment Summary (2026-07-24)
- E1: Prec_gate=1.000 at all thresholds. SS precision collapses to 0.333 at max aggressiveness. H1 confirmed.
- E2: **b=10, c=0, χ²=8.100, p=0.017**. FN-arm b=0,c=0 (honest tie). H2a confirmed. H2b honest.
- E3: −Control R_prop=0.10, −Knowledge R_prop=0.90, Prec_gate=1.000 all conditions. Directional (simulation).
- E4: Strix 0/5 flips, proxy 2/5 flips. H4 confirmed.
- 568 tests pass, 4 skipped. 10-pair corpus, all images built.

## Architecture
- Pattern: Docker-sandboxed agent with a Textual TUI CLI
- Pattern: Modular `strix/tools/` tool surface registered via `@function_tool` in `strix/agents/factory.py` `_BASE_TOOLS`
- Pattern: Pure, unit-testable boundary modules (`strix/core/net/`, `strix/core/identity/`, `strix/core/diff/`, `strix/core/oob/`, `strix/core/inventory/`, `strix/core/race/`, `strix/core/logic/`, `strix/core/proposals/`) with no Docker/network side effects
- Pattern: Impact-gated reporting — every `vulnerability_report` carries an `evidence_class ∈ {diff, callback, reachability, race_result, none}`; `none` downgrades. A separate `artifact_type` carries media/rendering type (do not conflate)
- Pattern: Deterministic harnesses (diff, OOB correlation, race harness, class sprays, business-logic orchestrator) with PBT invariants
- Pattern: **Agent-proposes / harness-disposes** — the LLM never self-confirms a finding; precision is owned by the harness, recall by the proposer. Enforced in *type structure* (the proposal stage carries no `evidence_class`/`ReportState`), not convention
- Pattern: Propose–Dispose funnel — `ProposalRecord`/`FunnelLog` in `report/proposals.py` records proposals + harness verdicts for the research metrics; additive to `report/state.py`, gate-neutral (`C ⊆ P`)

## Stack
- Python 3.12+ with strict mypy + Pyright + Ruff + Bandit (gate = clean on changed files; ~69 pre-existing TUI mypy errors deferred)
- Docker sandbox for agent execution and bundled security tools (pinned: gitleaks/trufflehog/trivy/ruff/pytest/interactsh)
- Caido proxy SDK for traffic capture and replay
- Pydantic v2 for models; openai-agents SDK for function-tool registration
- LiteLLM for provider routing; Rich/Textual for CLI/TUI

## Key Files
- `.agents/memory_bank/manifest.yml` — project DAG + execution state (local-only, gitignored; regenerated/revised per session)
- `.agents/specs/README.md` — program index and dependency graph
- `.agents/specs/strix-governance-layer/validation/pm-decision-s0-egress-gateway.md` — S0-v2 architecture decision (out-of-container egress gateway)
- `.agents/specs/strix-governance-layer/validation/coder-handoff-bringup-and-s0v2.md` — coder directive: Part A bring-up + Part B S0-v2
- `.agents/specs/strix-governance-layer/validation/verdict-11.md` — S3.1 breaker target-request health approved
- `.agents/api.txt` — LLM provider config (naraya/minimax-m3 via router.naraya.ai/v1)
- `strix/report/state.py` — `ReportState`, impact gate, `add_vulnerability_report` disposer→funnel link, additive `record_harness_run` emit-hook
- `strix/report/proposals.py` + `strix/core/proposals/` — `ProposalRecord`/`FunnelLog` + 4 pure metrics; flag-gated proposal-context assembler
- `strix/core/net/` — pure URL normalization + internal/metadata classification (P0)
- `strix/core/identity/` + `strix/core/diff/` — durable identity store + semantic differential engine (P1)
- `strix/core/oob/` + `strix/runtime/oob/` + `strix/tools/oob/` — token registry, correlator, interactsh sidecar (P2)
- `strix/core/inventory/` + `strix/tools/inventory/` — unified attack-surface inventory + reachability seam (P3)
- `strix/core/race/` — race-condition harness: dispatcher, precondition manager, commit-count aggregator, verdict (P4)
- `strix/core/logic/` + `strix/tools/logic/` — business-logic state-testing orchestrator + 5 tools (P5)
- `strix/core/govern/scope.py` — SGL-S1 fail-closed decision service (`decide`, `load_scope`); the single egress chokepoint, no LLM in path, no engine imports — **reuse in S0-v2 gateway**
- `strix/runtime/egress_proxy.py` — SGL-S0 transparent TCP + UDP-DNS decision proxy + F1 DNS→IP + S3.1 target-health recording — **reuse in S0-v2 gateway** (moves from agent container to gateway container)
- `containers/Dockerfile.gateway` — **NEW** S0-v2 egress-gateway image (python:3.12-slim + iptables + governance modules); REDIRECT-based transparent proxy
- `containers/gateway-entrypoint.sh` — **NEW** gateway entrypoint: nat PREROUTING REDIRECT for TCP+UDP-DNS, FORWARD DROP default, IPv6 FORWARD DROP via ip6tables, fails closed without `STRIX_AGENT_SUBNET`
- `strix/runtime/egress_proxy.py` — S0-v2 extensions: `--bind` (gateway mode), `--no-tproxy` (force REDIRECT mode), TPROXY socket option support (TCP/UDP), DNS NXDOMAIN for malformed queries, `_get_original_dst` selects `getsockname()` vs `SO_ORIGINAL_DST` based on `_tproxy_enabled`
- `containers/egress-enforcer.sh` — **UPDATED** single-container REDIRECT design: UDP filter fix (allow UDP to `PROXY_PORT` — REDIRECT changes dport before filter sees it); retained for single-container mode
- `containers/Dockerfile.prod` — **RETIRED** in-container iptables design
- `strix/runtime/docker_client.py` — **RETIRED** `user="root"` exec juggling; rewire for internal-network + gateway architecture pending
- `benchmarks/business_logic_fixture/` — seeded TP/TN fixture (`VULN_MODE` switch); reusable by Spec B's B-V2P corpus
- `.agents/specs/strix-governance-layer/` — SGL spec; `validation/` holds verdict-01/02/04/09/10/11 + completion reports + S0-v2 decisions

## Active Decisions
*(Newest first. Full table + rationale in ARCHITECTURAL_DECISIONS.md.)*
1. **[ARCH #19] S0-v2 gateway implementation complete:** REDIRECT-based transparent proxy in a dedicated egress-gateway container. Agent on internal Docker network; gateway on internal+bridge networks; iptables nat PREROUTING REDIRECT intercepts agent TCP+DNS UDP and delivers to proxy; proxy uses `SO_ORIGINAL_DST` + conntrack reverse-NAT to recover original destination. Single-container REDIRECT design (proxy + iptables OUTPUT) also retained for hermetic testing. TPROXY prototyped but abandoned for Docker Desktop (policy routing not available). Gateway mode works on real Linux hosts / Kubernetes where conntrack handles cross-container reverse-NAT. (2026-06-22, active)
2. **[ARCH #18] S0-v2 pivot:** in-container iptables RETIRED; enforcement moves to out-of-container egress gateway. Agent container on internal Docker network; gateway container is the sole egress path; scope enforced in gateway netns. Agent cannot reach/flush gateway rules. No run_as, no in-container iptables. Decision logic (scope/F1/breaker/Caido) reused. (2026-06-21, active)
3. **[ARCH #17] RETIRED:** governance modules in prod image via targeted COPY — retired because prod image restructures for S0-v2 gateway.
4. **[ARCH #16] RETIRED context:** `Defaults !authenticate` removed; 3-step sudo revocation — the sudo hardening was correct for the in-container design but is no longer needed in S0-v2 (agent can run as root harmlessly inside its own netns; the gateway is a separate container).
5. **[ARCH #11] Principle preserved, substrate retired:** enforcement at the container boundary (not app-layer) — correct principle; the iptables substrate location moves to the gateway container.
6. Canonical development diary is `active/PROGRESS.md` only; the stray root `memory_bank/PROGRESS.md` was consolidated and removed (2026-06-18, ARCH #10).
7. Funnel-completeness path (a): a minimal **additive, emit-only** hook (`ReportState.record_harness_run`) records every harness run — confirmed or not — so Spec B's `Prec_gate`/`funnel_efficiency` are unbiased; gate-neutral, disposer unmodified (2026-06-17, ARCH #9).
8. Propose–Dispose split into a product-DAG `unit` (instrumentation: funnel + assembler, keep-forever) and a NON-gating `research` spec (validation: corpus, ablation, experiments — contains the forbidden-in-prod M4 self-confirm mode, quarantined) (2026-06-16, ARCH #8).
9. Same-model validator override is operator-approved; verdicts are **method-carried** (executed checks + traced call graph), not lineage-carried. Producer provenance corrected to `opus-4.8` (the kimi label was a stale harness id) (2026-06-17, ARCH #6/#7).
10. Reuse-over-reimplement is a hard rule — every phase builds on prior primitives (P1 diff/identity, P2 OOB, P3 inventory, P4 race); no second differ, no new evidence class without explicit need (active since 2026-06-14).
11. `manifest.yml` is gitignored execution state, not version-controlled source (2026-06-14, ARCH #5).
12. Phase 0 foundation hardening was the first implementation priority; impact gate + pure validators precede all evidence-producing phases — now complete (2026-06-14, ARCH #4).
