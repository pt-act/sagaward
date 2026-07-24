# Coder Directive — SGL S2–S8, Then Deployment-Readiness for the Empirical Run

> From: PM/Validator (`opus-4.8-pm-auditor`) · To: Coder (CLI) · Re: strix bounty-grade engine
> **Updated 2026-06-19** — supersedes the prior SGL implementation directive.
> Branch for all remaining SGL work: **`sgl-s2-s8`** off `main @ e30778c`.
> Goal: implement SGL S2–S8 → reach Gate 5 HOLD LINE → file completion report.

---

## 0. Current state (what's done — do not redo)

- **Engine (P0–P5 + propose-dispose):** phases 0–5 + Spec A instrumentation + Spec B
  (M1/M2/M4 + harness wiring + emit hook) implemented and validated. Gate-neutrality
  `C ⊆ P` holds. M4 self-confirm quarantined/off by default.

- **SGL S0 + S1: DONE — squash-merged to `main @ e30778c` (PR #21, 2026-06-19).**
  - `strix/core/govern/scope.py` — fail-closed `decide()` + `load_scope()`; SP1/SP2
    Hypothesis-verified (500 + 900 examples, 0 counterexamples); 406 tests green.
  - `containers/Dockerfile.prod` + `containers/egress-enforcer.sh` +
    `strix/runtime/egress_proxy.py` — egress substrate authored (default-deny iptables +
    transparent TCP/DNS proxy; `USER pentester` exec default; `create_kwargs["user"]="root"`
    for entrypoint; full sudo revocation for pentester).
  - `strix/runtime/docker_client.py` — SGL env-injection + `user="root"` delta.

- **SP3 (image build + adversarial test):**
- The operator builds `strix-sandbox:prod` from `containers/Dockerfile.prod`  

- Run SP3.

- SP3 passing is the signal that S2 is safe to dispatch.

- **Not started (PM/operator step, NOT yours):** E1–E4 empirical run; E2 pre-registration
  lock; M0 live agent run.

Your job: **implement SGL S2–S8 → Gate 5 HOLD LINE → file completion report.**
Do not run experiments. Do not re-implement S0 or S1.

---

## 1. Wait for SP3 signal before starting S2

Do not begin S2 until the operator confirms SP3 passes:

```bash
docker run -d --name sgl-sp3 --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 -e STRIX_SCOPE_RULES="" strix-sandbox:prod
docker exec sgl-sp3 id -un                                    # → pentester
docker exec sgl-sp3 sh -c 'command -v sudo || echo NO-SUDO'   # → NO-SUDO
docker exec sgl-sp3 sh -c 'curl -s --max-time 5 https://example.com && echo BYPASS || echo BLOCKED'
docker rm -f sgl-sp3
```

When SP3 passes, branch off current main and begin S2.

---

## 2. Work order (S2–S8)

```
  main @ e30778c  (S0+S1 merged)
        │
        ▼  git switch -c sgl-s2-s8
  S2  Ownership attribution + rate/credential guardrails    ← start here (Sonnet)
  S3  Circuit breaker + kill-switch                         ← OPUS
  S4  Cost & value governor                                 ← Sonnet
  S5  Cross-engagement memory + dedup                       ← Sonnet
  S6  Governance audit log                                  ← Sonnet
  S7  Integration — wire decide() into Caido + replace _scope.py   ← OPUS
  S8  Gate-neutrality + full PBT suite SP1–SP10             ← OPUS
        │
        ▼
  Build B-V2P target images + Gate 5 HOLD LINE smoke
        │
        ▼  file completion report → hand to PM
   ── HOLD LINE ── PM validates, then runs E1–E4 on the hardened engine
```

**Producer routing — follow this, derived from validation experience:**
- **Opus:** S3 · S7 · S8 — security-infrastructure tasks requiring adversarial reasoning.
- **Sonnet:** S2 · S4 · S5 · S6 — deterministic Python service modules against clear specs.

**Hard invariant:** SGL may only remove actions upstream. Never alter a disposition, add an
`evidence_class`, or modify any file under `core/logic/`, `core/proposals/`, `core/oob/`,
`core/diff/`, `core/race/`. Prove with an import-boundary test.

---

## 3. SGL S2–S8 briefs (full spec + tasks in `.agents/specs/strix-governance-layer/`)

### S2 — Ownership + rate/cred guardrails (Sonnet)
- `govern/ownership.py` — ASN/CIDR/whois → confidence; θ=0.80; feeds `decide()`. Prop SP5.
- `govern/limiter.py` — 10 rps per-host (Retry-After-aware); cred cap 3/route/window,
  lockout-aware; integrate `core/inventory/spray.py`. Prop SP4.

### S3 — Circuit breaker + kill-switch (Opus)
- Hook `AgentCoordinator` (`core/agents.py`): extend `request_stop`/`cancel_descendants`.
- Trip: >25% error/20 reqs OR p95 >3× baseline; operator-ack to resume.
- Kill-switch halts in-flight including async OOB probes. Prop SP6 (zero-tolerance).

### S4 — Cost & value governor (Sonnet)
- Token/tool-call/spend ceilings (5M tokens + 10k calls; 80% backpressure, 100% halt)
  in `core/inputs.py`, `core/execution.py`. Expected-value queue ordering. Prop SP7.

### S5 — Cross-engagement memory + dedup (Sonnet)
- Per-engagement ledger (`tools/notes/`, `report/state.py`).
- Sanitized shared technique library; sanitizer extends `core/identity/redaction.py`.
- Known-issues dedup at emit; 90-day retention. Prop SP9.

### S6 — Governance audit log (Sonnet)
- Append-only allow/deny/halt + reason via `telemetry/logging.py`; replay reader. Prop SP10.

### S7 — Integration (Opus — highest-risk task in the spec)
- Route Caido HTTP path through `decide()` (`tools/proxy/`).
- Replace `_scope.py` callsites in `core/inventory/collectors/` with `decide()` — this
  finally fixes the fail-open bug in the live collection path.
- Confirm shell + browser egress traverse the S0 enforcer after wiring.
- Wire breaker/kill + governor into `AgentCoordinator` + agent loop.
- Import-boundary test: SGL imports nothing from `core/logic|proposals|oob|diff|race`.

### S8 — Gate-neutrality + full PBT suite (Opus)
- SP1–SP10 green; zero-tolerance SP1/SP2/SP3/SP6/SP8 = 0 counterexamples.
- Gate-neutrality on B-V2P pair: engine verdict flips vuln↔patch identically with/without SGL.

---

## 4. Build B-V2P target images (Gate-5 smoke)

```bash
docker build -t strix-bv2p-idor benchmarks/bv2p/idor_memories
docker build -t strix-bv2p-ssrf benchmarks/bv2p/ssrf_fetch
docker build -t strix-bl-fixture benchmarks/business_logic_fixture
```

Verify `VULN_MODE` flip on each. Confirm targets are in engagement scope for the smoke.

---

## 5. Gate 5 HOLD LINE (authorized lab targets only)

- [ ] `docker exec` → pentester; sudo absent; egress to un-allowed host → BLOCKED.
- [ ] Out-of-scope → 0; destructive → 0.
- [ ] Gate-neutrality: confirmed set identical with/without SGL on B-V2P pair.
- [ ] Kill-switch halts in-flight; breaker trips and requires operator ack.
- [ ] End-to-end run under cost ceiling.

**Until every row passes, E1–E4 do not start.**

---

## 6. Reproducibility gaps (carry forward)

- **F-3 (major):** pin pyright in `.pre-commit-config.yaml`; re-run over `strix/core/govern/`.
- **F-1 (major):** add OOB expiry-window true-negative regression (`core/oob/correlator.py:57`).
- **F-4 (minor):** fix order-dependent mock at `tests/test_identity_replay.py:34`.
- **F-2 (minor, note only):** correct `_is_bfla` comment; do not fix logic without spec change.

---

## 7. Pre-registration (operator gate — surface it, don't decide it)

`E2-preregistration.md` is Status: DRAFT. Lock against the `sgl-s2-s8` HEAD. Record the sha
in your report. E1/E3/E4 + M0 may proceed before lock; only reading E2 results is gated.

---

## 8. Definition of Done

**A — SGL S2–S8 (`sgl-s2-s8` branch):**
- [x] S0+S1 on `main @ e30778c` — done.
- [ ] S2–S8 complete; AC-G3–G9 met; SP1–SP10 green; SP1/SP2/SP3/SP6/SP8 zero CE.
- [ ] Gate-neutrality: import-boundary test green; B-V2P confirmed-set diff = ∅.

**B — Deployment-readiness:**
- [ ] SP3 passed (operator confirms; you attest in report).
- [ ] Boot smoke passes (interactsh PID + "Caido API is ready").
- [ ] Image tagged deterministically; `runtime.image` reconciled (not ghcr `1.0.0`).
- [ ] B-V2P + business-logic images build; `VULN_MODE` flip verified.
- [ ] Gate 5 HOLD LINE (§5) — all rows pass.

**C — Repro + report:**
- [ ] F-3 pinned or deferred; F-1 added or deferred; F-4/F-2 noted.
- [ ] Completion report filed per §9.

---

## 9. Completion report stub

Path: `.agents/specs/strix-governance-layer/validation/sgl-s2-s8-completion-report.md`
Per VALIDATION_PROTOCOL.md §C — per-criterion Claim + Evidence; malformed reports returned unread.

```markdown
# Completion Report — SGL S2–S8 + deployment readiness

## Header
producer: <interpreter id>
started / completed: <UTC>
baseline: main @ e30778c (S0+S1)
sgl-s2-s8 HEAD: <sha>

## Artifacts Produced
- strix-sandbox:prod (digest sha256:...; egress active; SP3 passed)
- strix-bv2p-idor / strix-bv2p-ssrf / strix-bl-fixture (digests)
- strix/core/govern/ownership.py, govern/limiter.py  (S2)
- core/agents.py delta  (S3)
- core/inputs.py / core/execution.py delta  (S4)
- tools/notes/ / report/state.py delta  (S5)
- telemetry/logging.py delta  (S6)
- tools/proxy/ + _scope.py replacement  (S7)

## Acceptance Criteria Self-Check
- Criterion: SP1–SP10 green; SP1/SP2/SP3/SP6/SP8 zero CE
  - Claim: met | Evidence: <Hypothesis summary; per-property CE count>
- Criterion: Gate-neutrality — import-boundary + B-V2P diff = ∅
  - Claim: met | Evidence: <import-boundary output; confirmed-set comparison>
- Criterion: SP3 adversarial test (operator-confirmed)
  - Claim: met | Evidence: <id -un → pentester; NO-SUDO; egress BLOCKED>
- Criterion: Gate 5 HOLD LINE
  - Claim: met | Evidence: <per-row results>
- Criterion: F-1 / F-3 (+ F-2/F-4 notes)
  - Claim: met | deferred | Evidence: <test name or deferral rationale>

## Known Deviations
<anything deferred; corpus choice>

## Handoff Notes
<sgl-s2-s8 HEAD sha for E2 lock; image tag; runtime.image setting>
```

---

## Out of scope
- E1–E4 (PM, after Gate 5). E2 lock (operator). Disposer/evidence-class changes (forbidden).

When §8 A+B+C are checked and §9 filed, hand back to the PM.
