# Coder Directive — SGL-Core to the HOLD LINE (v2)

> From: PM/Validator (`opus-4.8-pm-auditor`) · To: Coder (CLI) · Re: strix bounty-grade engine
> **v2, 2026-06-20** — supersedes the 2026-06-19 SGL S2–S8 directive. Folds in the PM review of
> the merged S0+S1 code (the egress ALLOW-path gap) and an explicit **Core/Plus scope split**.
> Branch for remaining SGL-Core work: **`sgl-s2-s8`** off `main @ f49d59f`.
> Goal: implement **SGL-Core** → reach Gate 5 HOLD LINE → file completion report.

---

## PM engineering decisions (rationale — read first)

These are PM calls, made so the project reaches a *safe-to-run-unattended* state fast, without
shipping risk it doesn't need yet. They are glass-box on purpose.

1. **Scope is split: SGL-Core ships to the HOLD LINE; SGL-Plus is deferred.**
   - **Core** = the containment envelope that makes unattended operation safe: fail-closed
     egress (S0/S1, done) + ownership/rate/cred (S2) + breaker/kill-switch (S3) + a hard
     **cost ceiling→halt** (S4a) + audit (S6) + integration (S7) + gate-neutrality/PBT (S8).
   - **Plus (deferred — separate later branch)** = expected-value **queue ordering** (S4b) and
     the **cross-engagement shared memory / technique library** (S5).
   - *Why:* S4b and S5 are optimization/knowledge features, not safety. S5 specifically adds a
     cross-client data-leak surface (the audit-prep's own threat list) and cannot make an
     unattended run safe or unsafe — so it must not gate the HOLD LINE or the paper. Deferring
     them removes ~3–4 iterations and the highest-risk surface from the critical path.

2. **F1 (egress ALLOW-path) is fixed with DNS→IP correlation, and is release-gating for S7.**
   The merged egress proxy decides on the destination **IP** (`SO_ORIGINAL_DST`) with no link
   to the hostname the agent resolved. So a **hostname** scope rule (`example.com`) is matched
   at the DNS layer but the subsequent TCP-by-IP check fails → the connection is DENIED.
   Operators scope by hostname, so this must be corrected, not worked around. See S7.F1.

3. **SP3 must test the ALLOW direction, not only deny-all.** The current gate only proves
   "empty scope → everything blocked" (the easy half). It must also prove a hostname-scoped
   ALLOW works, and cover IPv6 + non-DNS UDP. See §1.

**Net effect:** the coder builds S2 → S3 → S4a → S6 → S7(+F1) → S8 to Gate 5; S4b and S5 are a
follow-on the operator schedules after the paper (or in parallel, off the critical path).

---

## 0. Current state (done — do not redo)

- **Engine (P0–P5 + propose-dispose):** implemented, validated, merged. Gate-neutrality `C ⊆ P`
  holds; M4 self-confirm quarantined/off by default.
- **SGL S0 + S1: DONE — on `main @ f49d59f`** (PR #21 `e30778c` + prod-image hardening
  `1e0f77b`/`f49d59f`).
  - `strix/core/govern/scope.py` — fail-closed `decide()` + `load_scope()` (SP1/SP2 verified).
  - `strix/runtime/egress_proxy.py` + `containers/egress-enforcer.sh` + `Dockerfile.prod` —
    egress substrate (default-deny iptables + transparent TCP via `SO_ORIGINAL_DST` + a UDP/53
    DNS decision protocol); pentester sudo fully revoked; entrypoint runs as root, agent runs
    sudo-less via `docker exec`.
  - `strix/runtime/docker_client.py` — `STRIX_EGRESS_ENFORCE`/`STRIX_SCOPE_RULES` injection.
- **Known issue carried into S7 (PM review of S0/S1):** the egress **ALLOW path is
  IP-based with no DNS→IP correlation** (F1). The deny/fail-closed direction is sound; the
  allow-by-hostname direction is broken until S7.F1 lands.
- **Not yours (PM/operator):** E1–E4 empirical run; E2 pre-registration lock; M0 live agent run.

Your job: **implement SGL-Core (S2, S3, S4a, S6, S7+F1, S8) → Gate 5 HOLD LINE → completion
report.** Do not run experiments. Do not re-implement S0/S1. Do not build S4b or S5.

---

## 1. SP3 gate — strengthened (run before starting S7; S2–S6 may proceed in parallel)

The S0 egress substrate is the safety foundation; prove it both directions before integration.
Operator builds `strix-sandbox:prod` from `containers/Dockerfile.prod`, then:

```bash
# DENY direction (empty scope ⇒ everything blocked)
docker run -d --name sgl-sp3 --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 -e STRIX_SCOPE_RULES="" strix-sandbox:prod
docker exec sgl-sp3 id -un                                          # → pentester
docker exec sgl-sp3 sh -c 'command -v sudo || echo NO-SUDO'        # → NO-SUDO
docker exec sgl-sp3 sh -c 'curl -s --max-time 5 https://example.com && echo BYPASS || echo BLOCKED'   # BLOCKED
docker exec sgl-sp3 sh -c 'nmap -sT -p80 example.com >/dev/null 2>&1 && echo BYPASS || echo BLOCKED'  # BLOCKED
docker exec sgl-sp3 sh -c 'dig +time=3 @8.8.8.8 example.com >/dev/null 2>&1 && echo BYPASS || echo BLOCKED'  # BLOCKED
docker exec sgl-sp3 sh -c 'curl -6 -s --max-time 5 "http://[2606:2800:220:1:248:1893:25c8:1946]" && echo BYPASS || echo BLOCKED'  # BLOCKED (IPv6)
docker exec sgl-sp3 sh -c 'curl -s --max-time 5 ntp://pool.ntp.org && echo BYPASS || echo BLOCKED'   # BLOCKED (non-DNS UDP path)
docker rm -f sgl-sp3

# ALLOW direction (hostname-scoped ⇒ must succeed — THIS is the F1 check; passes only after S7.F1)
docker run --rm --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 -e STRIX_SCOPE_RULES="example.com" \
  strix-sandbox:prod sh -c 'curl -s --max-time 8 https://example.com | head -1'   # → HTML
```

- **Deny rows gate S2 dispatch** (they pass on the current `main`).
- **The hostname-ALLOW row gates Gate 5** and passes only after S7.F1 lands. Until then, record
  it as a known-failing functional gap, not a safety gap (it over-blocks).

---

## 2. Work order — SGL-Core

```
  main @ f49d59f  (S0+S1 merged)
        │  git switch -c sgl-s2-s8
        ▼
  S2   Ownership attribution + rate/credential guardrails        ← Sonnet
  S3   Circuit breaker + kill-switch                             ← OPUS
  S4a  Cost ceiling → halt (the safety half of S4)               ← Sonnet
  S6   Governance audit log                                      ← Sonnet
  S7   Integration + F1 egress DNS→IP fix  (highest-risk task)   ← OPUS
  S8   Gate-neutrality + full PBT suite SP1–SP10                 ← OPUS
        │
        ▼  build B-V2P target images → Gate 5 HOLD LINE smoke
        ▼  file completion report → hand to PM
   ── HOLD LINE ── PM validates, then runs E1–E4 on the hardened engine

  DEFERRED (SGL-Plus, separate branch, post-paper or parallel — NOT this directive):
  S4b  expected-value queue ordering   ·   S5  cross-engagement memory + shared technique library
```

**Producer routing (keep):** Opus on S3 · S7 · S8 (adversarial security reasoning). Sonnet on
S2 · S4a · S6 (deterministic service modules against clear specs).

**Hard invariant (prove with an import-boundary test in S7/S8):** SGL may only *remove* actions
upstream. Never alter a disposition, add an `evidence_class`, or modify any file under
`core/logic/`, `core/proposals/`, `core/oob/`, `core/diff/`, `core/race/`.

---

## 3. SGL-Core briefs (full spec/tasks in `.agents/specs/strix-governance-layer/`)

### S2 — Ownership + rate/cred guardrails (Sonnet) · AC-G3/G4 · SP4/SP5
- `govern/ownership.py` — ASN/CIDR/whois → ownership confidence; default **θ=0.80**; feeds
  `decide()` (below θ ⇒ not ALLOW). Guard the classic mis-attribution cases the audit-prep
  lists: shared hosting, CDN ranges, acquired/divested subsidiaries — when ownership is
  ambiguous, resolve to **needs-approval (DENY)**, not ALLOW.
- `govern/limiter.py` — per-host **10 rps** (honors `Retry-After`/backoff); credential cap
  **3/route/window**, lockout-aware. Integrate `core/inventory/spray.py`. **Concurrency-safe:**
  the agent graph runs children in parallel — the cred cap must hold under concurrent children
  (no race past the cap). Tests: SP4 (rate/cred bound under burst *and* concurrency), SP5
  (ownership gating).

### S3 — Circuit breaker + kill-switch (Opus) · AC-G5 · SP6 (zero-tolerance)
- Hook `AgentCoordinator` (`core/agents.py`): extend `request_stop`/`cancel_descendants`.
- Trip on target-health breach: error-rate **>25%/20 reqs** OR p95 latency **>3× baseline**;
  resume requires **operator ack**.
- Kill-switch halts in-flight actions **including async OOB probes and parallel child agents** —
  no action may complete after a kill, no child may outlive the halt. This race is the SP6 audit
  focus; test it explicitly.

### S4a — Cost ceiling → halt (Sonnet) · AC-G6 (safety subset) · SP7
- Token/tool-call/spend accounting beyond `max_turns`, in `core/execution.py`/`core/inputs.py`.
- Ceilings: **5M tokens + 10k tool-calls/engagement**; **80% backpressure, 100% halt**.
- **No value-ordering here** — a hard cap that halts is the safety control; expected-value queue
  ordering is S4b (deferred). Test: SP7 (spend ≤ ceiling; exhaustion ⇒ halt; no action left
  half-executed at the ceiling).

### S6 — Governance audit log (Sonnet) · AC-G9 · SP10
- Append-only allow/deny/halt + reason via `telemetry/logging.py`; replay reader linking each
  decision to its action. Test: SP10 (every decision ⇒ exactly one audit entry; replayable).

### S7 — Integration + F1 egress fix (Opus — highest-risk task) · AC-G2/G8 wiring · SP3/SP8
1. **F1 — DNS→IP correlation in the egress proxy (release-gating).** In
   `strix/runtime/egress_proxy.py`:
   - On a DNS **ALLOW**, record the resolved A/AAAA IP(s) in a **short-TTL per-engagement
     resolved-IP allow-set** (TTL = min(record TTL, a hard cap e.g. 300s)).
   - The TCP handler authorizes a connection if the destination IP matches a direct IP/CIDR
     scope rule **OR** is currently in the resolved-IP allow-set. Otherwise **DENY** (still
     fail-closed).
   - **DNS-rebinding defense:** do **not** add a resolved IP to the allow-set if it is private/
     loopback/link-local/metadata — reuse `strix.core.net.is_internal_target` — unless that
     range is *explicitly* in scope. An in-scope hostname must not be able to authorize
     169.254.169.254 or 10.0.0.0/8 by resolving there.
   - Tests (Tier-1 + a PBT): hostname in scope → DNS ALLOW → IP added → TCP to that IP ALLOW;
     hostname out of scope → NXDOMAIN → IP never added → TCP to that IP DENY; in-scope hostname
     resolving to a private/metadata IP → TCP DENY (rebinding); allow-set entry expires ⇒
     subsequent TCP DENY.
2. Route the Caido HTTP path through `decide()` (`tools/proxy/`).
3. **Replace the fail-open `host_in_scope` callsites** in `core/inventory/collectors/` and
   `core/race/dispatch.py` with `decide()` — this finally closes the audited fail-open bug on
   the live collection + race paths (F2 from the S0/S1 review). After this, grep the tree for
   any remaining `return True` default or `if not scope_rules:` short-circuit (audit-prep item).
4. Confirm shell + browser egress still traverse the S0 enforcer after wiring (no app-layer
   bypass introduced).
5. **Import-boundary test:** SGL imports nothing from `core/logic|proposals|oob|diff|race`.

### S8 — Gate-neutrality + full PBT suite (Opus) · AC-G8 · SP8 (zero-tolerance)
- SP1–SP10 green under Hypothesis; **zero-tolerance SP1/SP2/SP3/SP6/SP8 = 0 counterexamples.**
- **Gate-neutrality on a B-V2P pair:** the engine verdict must flip vuln↔patch **identically**
  with and without SGL present, for SGL-allowed actions. Note for the PM (not a code task): SP8
  proves *precision* (disposition) neutrality; it does **not** prove recall neutrality — the
  limiter/cost-cap can suppress actions. The paper runs use a **non-binding measurement profile**
  (enforcement on; rate/cost ceilings set high enough not to bind). State this in the report.

---

## 4. Build B-V2P target images (for the Gate-5 smoke)

```bash
docker build -t strix-bv2p-idor benchmarks/bv2p/idor_memories
docker build -t strix-bv2p-ssrf benchmarks/bv2p/ssrf_fetch
docker build -t strix-bl-fixture benchmarks/business_logic_fixture
```
Verify the `VULN_MODE` flip on each, and that each target's host is **in engagement scope** for
the smoke (otherwise the now-correct enforcer will block it — that's the point).

---

## 5. Gate 5 — HOLD LINE (authorized lab targets only: Juice Shop / DVWA-class + consented CTF)

- [ ] `docker exec` → pentester; sudo absent; egress to an un-allowed host → BLOCKED.
- [ ] **Hostname-scoped in-scope target → ALLOWED** (the F1 check; end-to-end run reaches it).
- [ ] Out-of-scope actions → 0; destructive actions → 0; egress-bypass attempts → 0 reach network.
- [ ] Gate-neutrality: confirmed set identical with/without SGL on a B-V2P pair (verdict still flips).
- [ ] Kill-switch halts in-flight (incl. async OOB + child agents); breaker trips + requires ack.
- [ ] End-to-end run completes under the cost ceiling.

**Until every row passes, E1–E4 do not start.**

---

## 6. Reproducibility gaps (carry forward — from the prior reviews)

- **F-3 (major):** pin pyright in `.pre-commit-config.yaml`; re-run over `strix/core/govern/`.
- **F-1-OOB (major):** add the OOB expiry-window true-negative regression
  (`core/oob/correlator.py:57`) — an expired callback ⇒ unconfirmed/no report.
- **F-4 (minor):** fix the order-dependent module-level mock at `tests/test_identity_replay.py:34`.
- **F-2-BFLA (minor, note only):** correct the misleading "true BFLA" test comment; do **not**
  change `_is_bfla` logic without a spec change.

---

## 7. Pre-registration (operator gate — surface, don't decide)

`E2-preregistration.md` is Status: DRAFT. Lock it against the `sgl-s2-s8` HEAD; record the sha in
your report. E1/E3/E4 + M0 may proceed before lock; only **reading E2 results** is gated.

---

## 8. Definition of Done — SGL-Core

**A — SGL-Core (`sgl-s2-s8` branch):**
- [ ] S2, S3, S4a, S6, S7(+F1), S8 complete; AC-G3/G4/G5/G6(cap)/G9 met.
- [ ] SP1–SP10 green; SP1/SP2/SP3/SP6/SP8 zero counterexamples.
- [ ] F1: hostname-scoped ALLOW works; DNS-rebinding denied; fail-open `host_in_scope` callsites
      replaced; tree grep clean of fail-open short-circuits.
- [ ] Gate-neutrality: import-boundary test green; B-V2P confirmed-set diff = ∅.

**B — Deployment-readiness:**
- [ ] SP3 (§1) passes **both directions** (deny rows + hostname-ALLOW row).
- [ ] Boot smoke: interactsh PID up + "Caido API is ready".
- [ ] Image tagged deterministically (e.g. `strix-sandbox:<sgl-s2-s8-sha>`); `runtime.image`
      reconciled (not ghcr `1.0.0`).
- [ ] B-V2P + business-logic images build; `VULN_MODE` flip verified.
- [ ] Gate 5 HOLD LINE (§5) — all rows pass.

**C — Repro + report:**
- [ ] F-3 pinned (or deferred w/ rationale); F-1-OOB added (or deferred); F-4/F-2 noted.
- [ ] Completion report filed per §9.

**Explicitly NOT in this directive (SGL-Plus, deferred):** S4b expected-value queue ordering; S5
cross-engagement memory + shared technique library. Do not implement them here.

---

## 9. Completion report stub

Path: `.agents/specs/strix-governance-layer/validation/sgl-core-completion-report.md`
Per VALIDATION_PROTOCOL.md §C — per-criterion **Claim + Evidence**; malformed reports returned unread.

```markdown
# Completion Report — SGL-Core + deployment readiness

## Header
producer: <interpreter id(s) — note Opus/Sonnet per group>
started / completed: <UTC>
baseline: main @ f49d59f (S0+S1)
sgl-s2-s8 HEAD: <sha>

## Artifacts Produced
- strix-sandbox:<sha> (digest sha256:...; egress active; SP3 both-direction pass)
- strix-bv2p-idor / strix-bv2p-ssrf / strix-bl-fixture (digests)
- govern/ownership.py, govern/limiter.py            (S2)
- core/agents.py delta                              (S3)
- core/execution.py / core/inputs.py delta          (S4a)
- telemetry/logging.py delta                        (S6)
- egress_proxy.py F1 delta + tools/proxy/ + _scope.py callsite replacement  (S7)

## Acceptance Criteria Self-Check  (one block each)
- SP1–SP10 green; SP1/SP2/SP3/SP6/SP8 zero CE   — Claim/Evidence: <Hypothesis summary + CE counts>
- F1 egress: hostname ALLOW + rebinding DENY    — Claim/Evidence: <test names + SP3 ALLOW row output>
- fail-open closed (host_in_scope replaced)     — Claim/Evidence: <grep clean; callsite diff>
- Gate-neutrality (import-boundary + B-V2P diff=∅) — Claim/Evidence: <outputs>
- Breaker/kill incl. async + children (SP6)     — Claim/Evidence: <race test>
- Cost ceiling halt (SP7)                        — Claim/Evidence: <exhaustion test>
- Gate 5 HOLD LINE                               — Claim/Evidence: <per-row results>
- F-3 / F-1-OOB (+ F-2/F-4 notes)               — Claim/Evidence: <test name or deferral>

## Known Deviations
<SGL-Plus S4b/S5 deferred by PM decision; corpus = fixtures vs upstream; anything else>

## Handoff Notes
<sgl-s2-s8 HEAD sha for E2 lock; image tag; runtime.image setting; measurement-profile note for the paper>
```

---

## Out of scope
- E1–E4 (PM, after Gate 5). E2 lock (operator). Disposer/evidence-class changes (forbidden).
- SGL-Plus (S4b queue ordering, S5 cross-engagement memory) — a later directive.

When §8 A+B+C are checked and §9 is filed, hand back to the PM for validation, then the E1–E4 run.
