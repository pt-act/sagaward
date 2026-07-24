# Phase 2 — Native OOB Oracle — Requirements (Planning)

> Spec-Architect PBT variant · Phase 2 of the strix bounty-grade engine.
> Primitive: **P3** (OOB oracle). Feature **F2** (native out-of-band support).
> Sequenced early: it is the **truth oracle** that keeps an LLM agent honest — later phases confirm rather than guess.

---

## Problem / Intent

An LLM agent is structurally prone to *confident nonsense* on blind vulnerability classes. SSRF, XXE, blind XSS, async callbacks, and webhook abuse share one defining trait: the proof of exploitation **does not come back in the HTTP response** the agent can see. It arrives out-of-band — as a DNS lookup or an inbound HTTP(S) request to an attacker-controlled endpoint. Without a listener it controls, the agent can only reason *"this looks injectable"* and promote a finding on static suspicion — exactly the anti-pattern the roadmap forbids (§6: "promoting findings on static suspicion").

Today strix bundles the `interactsh-client` binary in the container image (`containers/Dockerfile`) but has **no first-class workflow**: no self-hosted listener it owns, no per-finding token minting, no correlation of an inbound hit back to the request that caused it, and no gate that blocks a blind candidate from becoming a finding until a callback is observed. Relying on third-party hosted interactsh (`oast.fun` et al.) leaks target information to an external service and is unacceptable for bounty engagements.

The intent of Phase 2 is to give the agent **P3 — a native OOB oracle**:

- A **self-hosted interactsh-style listener** running as a sidecar in `strix/runtime/oob/`, capturing inbound **DNS** and **HTTP(S)** interactions on a domain strix controls.
- **Per-finding callback-token minting**: each injection attempt gets a unique token bound to exactly one finding-candidate, embedded in the payload the agent injects.
- A **correlation engine** that attributes each inbound hit back to the originating request / finding-candidate via its token.
- OOB wired as the **standard confirmation path** for SSRF, XXE, blind XSS, async callbacks, and webhook abuse.
- A hard **impact gate**: a blind-injection candidate is promoted to a confirmed finding **only when a correlated callback is observed** within its window.

This makes "the agent proposes, a deterministic harness disposes" concrete for the blind classes: the agent injects, the listener+correlator dispose. No callback, no finding.

---

## Beneficiaries

| Beneficiary | Benefit |
|---|---|
| The strix LLM agent | Gains a deterministic oracle it can compose (mint token → inject → wait → confirm) instead of hallucinating "looks exploitable" verdicts on blind classes. |
| The human bounty operator | Receives blind-class findings backed by a real callback (a captured DNS/HTTP hit), not narrative speculation; false-positive rate on blind classes drops measurably (roadmap Phase 2 exit criteria). |
| Downstream phases | Phase 5 (business-logic) reuses the P3 callback as one of its three permitted evidence types; Phase 3 inventory feeds candidate sinks; Phase 4 can confirm async/webhook races via callbacks. |
| The report layer | Receives impact-gated evidence (a correlated callback record) to attach to a `vulnerability_report` (`strix/report/state.py`). |

---

## Core Functionality

1. **Self-hosted OOB listener (sidecar).** A listener strix owns, capturing inbound **DNS** queries and **HTTP(S)** requests to a controlled domain, recording per-interaction metadata: protocol, full token-bearing FQDN/path, source IP, timestamp, and raw request. Runs as a sidecar mirroring the in-container Caido pattern (`strix/runtime/caido_bootstrap.py`, `session_manager.py`), reusing the SDK's exposed-port + host-gateway wiring (`strix/runtime/docker_client.py`).
2. **Token mint & registry.** Mint a **unique** callback token per injection attempt; bind it to exactly one finding-candidate (and the originating request). Each token yields an injectable interaction host (e.g. `<token>.<oob-domain>`) and a registry row recording {token, candidate-id, request ref, mint time, window, vuln-class hypothesis}.
3. **Correlation engine.** For each inbound hit, extract the token, look it up in the registry, and **attribute** the hit to its candidate. Reject/quarantine hits whose token was never minted (no attribution without a prior mint). Surface correlation as a structured record (token, candidate, protocol, source, timestamp, latency-from-mint).
4. **Injection helpers.** Class-specific helpers that embed a minted interaction host into a payload for SSRF (URL param/Host/redirect target), XXE (external entity SYSTEM URL), blind XSS (callback `src`/fetch), async callbacks and webhook abuse (callback-URL fields). The agent composes; helpers only template the token in.
5. **Confirmation gate (impact-gating).** A candidate is **confirmed** iff a correlated callback for its token is observed within the candidate's window; otherwise it remains **unconfirmed** and **must not** be reported as confirmed. Confirmation attaches the callback record as evidence into `strix/report/state.py`.
6. **Agent tool surface (P3 → F2).** `@function_tool`s mirroring `strix/tools/proxy` conventions: mint a token for a candidate, poll/await correlated hits for a token, and a one-shot "inject-and-confirm" helper that mints → returns the host for injection → reports the correlated result (or a clean negative within the window).

---

## User Stories

- **As the strix agent**, I want to mint a unique callback token bound to one SSRF candidate, so that any inbound hit on that token unambiguously confirms *that* candidate and no other.
- **As the strix agent**, I want to inject a token-bearing host into an XXE external-entity payload and then be told whether the listener saw a DNS/HTTP callback, so that I confirm blind XXE with evidence instead of guessing.
- **As the strix agent**, I want a blind-XSS candidate to stay unconfirmed until a browser actually calls back, so that I never report a stored-XSS finding the application never executed.
- **As the human operator**, I want the listener self-hosted on a domain I control, so that no target data leaks to a third-party hosted interactsh service.
- **As the human operator**, I want every confirmed blind-class finding to carry the exact captured callback (protocol, source IP, timestamp, token), so that I can verify it in seconds.
- **As a downstream phase**, I want to request "give me a token and tell me if it fired", so that I reuse P3 as my async/webhook evidence source instead of reinventing it.

---

## Constraints

- **Self-hosting.** The listener must be strix-owned (sidecar in `strix/runtime/oob/`); third-party hosted interactsh (`oast.fun`, public servers) is explicitly out of scope. Operator supplies the OOB domain + its delegation.
- **DNS control.** Confirming OOB-DNS requires the operator to delegate a domain (NS records) to the listener; the spec assumes this is configured. Where DNS delegation is unavailable, HTTP(S)-only OOB still functions and is the documented fallback.
- **Network egress from the sandbox.** The target (or its server-side fetcher) must be able to reach the listener's public IP/domain. Egress is target-controlled and not guaranteed; an absent callback within the window is treated as *unconfirmed*, never as *confirmed-negative-proof-of-safety*.
- **WHAT, not HOW** in `spec.md`; no code bodies. **Estimates in iterations**, never time.
- **Impact-gating is non-negotiable:** no callback within window → not reportable as confirmed.
- **Glass-box:** every mint, every inbound hit, and every correlation decision is recorded and inspectable; confirmation is never a black-box verdict.
- **Token unforgeability / scoping:** tokens are unguessable and minted only by strix; a hit with an unminted token is never attributed. Tokens are per-engagement scoped.
- **Determinism:** the token registry and the correlation function are pure/deterministic given (mint log, hit log) so they are PBT-testable and reproducible.
- **Component size:** backend modules cohesive/single-responsibility; any TUI surface ≤ 400 lines.
- **Test budget:** 16–34 focused tests total; security-critical cores additionally covered by Tier-2 PBT.

---

## Reusable strix code (reuse before build)

| Module | What it gives us | Use in Phase 2 |
|---|---|---|
| `containers/Dockerfile` | Already installs `interactsh-client` (ProjectDiscovery) + `dnsutils`, `netcat`, Go toolchain; runs `docker-entrypoint.sh` | Listener sidecar can run a self-hosted interactsh server / equivalent inside the same image; no new base tooling needed. |
| `strix/runtime/caido_bootstrap.py` | In-container sidecar bootstrap pattern: start service, retry-probe readiness, grab a host-side handle via exposed port | Direct template for the OOB listener bootstrap + readiness probe. |
| `strix/runtime/session_manager.py` | `create_or_reuse`, `_CONTAINER_CAIDO_PORT`, per-scan session cache | Mirror for an OOB listener port + per-scan lifecycle. |
| `strix/runtime/docker_client.py` | `StrixDockerSandboxClient`: exposed-ports, `host.docker.internal` host-gateway, NET_ADMIN/NET_RAW caps | Expose the listener's DNS/HTTP ports; reach host-served test apps. |
| `strix/runtime/backends.py` | `get_backend`, `_docker_backend`, `exposed_ports` plumbing | Wire the OOB listener's ports through the existing backend abstraction. |
| `strix/tools/proxy/tools.py` | `@function_tool`, `_ctx_client`, `_to_tool_json`, `_err`, JSON-string returns | Shape of the new mint / poll / inject-and-confirm tools so they plug in identically. |
| `strix/report/state.py` | `add_vulnerability_report(title, severity, …, poc_description, target, endpoint, method)`, `vulnerability_reports` | Impact-gating sink: attach the correlated callback as PoC evidence. |
| `strix/core/{paths,runner,inputs}.py` | run orchestration + path helpers | Durable per-engagement token-registry location and run wiring. |
| `strix/core/sessions.py` | `SQLiteSession` durable per-id store pattern | Mirror for the durable token registry (mint log + hit log). |
| `tests/test_core_paths.py` | unittest + spec-loaded-module regression pattern | Mirror for Tier-1 tests. |

---

## Risks / Assumptions

**Assumptions**
- The operator delegates an OOB domain (NS records) to the listener for full DNS+HTTP coverage; HTTP(S)-only is the documented fallback when DNS delegation is absent.
- The listener has a reachable public IP/domain from the target's perspective (the whole point of OOB); reachability is target-controlled and may legitimately be blocked.
- `interactsh-client`/server (already in the image) or an equivalent self-hosted listener can be driven from the sidecar; we do **not** depend on ProjectDiscovery's hosted servers.
- Inbound hits carry the token recoverably (subdomain label for DNS, host/path for HTTP) — the standard interactsh correlation-id scheme.

**Risks**
- **False confirmation from a stray/replayed hit** (e.g. an unminted token, or a benign scanner) → mitigated by the *correlation-correctness* and *token-binding* invariants: only minted tokens attribute, each to exactly one candidate.
- **Token collision / reuse across candidates** → mitigated by the *token-uniqueness/binding* invariant (unguessable, one-to-one mint).
- **Missed callback inside the window treated as proof of safety** → explicitly forbidden: absence is *unconfirmed*, never *safe*. The *no-false-confirm* invariant only blocks promotion; it does not assert safety.
- **Cross-engagement token leakage** (a hit for engagement A attributed to B) → per-engagement token scoping; registry keyed by engagement.
- **Listener downtime losing a real callback** → uptime is a non-functional requirement; the readiness probe (mirroring caido_bootstrap) gates injection on a live listener, and mints are rejected while the listener is down.
- **Third-party-interactsh temptation** → hard out-of-scope line; self-hosted only, to avoid leaking target data.
- **DNS-only environments / egress filtering** → HTTP(S) and DNS are independent capture paths; a hit on either confirms.
