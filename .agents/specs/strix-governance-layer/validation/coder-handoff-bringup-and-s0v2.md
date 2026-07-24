# Coder Directive — Strix Engine Bring-Up + S0-v2 Out-of-Container Egress Gateway

> From: PM/Validator (`opus-4.8-pm-auditor`) · To: Producer (CLI) · 2026-06-21
> Producer routing: **Opus** — this is network/containment architecture + operational bring-up of a
> never-launched engine. Not a Sonnet/cheaper-model task.
> Read with: `pm-decision-s0-egress-gateway.md`, verdicts 09–11, `pm-decision-breaker-target-health.md`.
> Operator decisions driving this: (1) bring-up handed to a producer; (2) **containment (S0-v2) must
> be live-proven before any paper/empirical/real-target run.** Debug/build runs to GET there are
> expected and fine — "no more runs" means no *data-collection / unattended / non-owned-target* runs
> until S0-v2's containment is proven.

---

## Context — read first (the why)

- **Governance logic is done and merged** (SGL-Core: `scope`, `ownership`, `limiter`, `breaker`,
  `cost_ceiling`, `audit`, F1 DNS→IP, the Caido `decide()` gate, S3.1 target-health). Unit-validated
  (verdicts 09–11). All of it is **reusable** — none of it is being thrown away.
- **The in-container egress-firewall approach is RETIRED.** Three live integration failures proved it
  incompatible with strix's *injected-session* SDK model:
  - PRE-3: the agent execs as **root** (the SDK uses the container create-user for exec), and root is
    uid-0-exempt from the in-container iptables redirect AND can `iptables -F` it.
  - The fix for PRE-3 — `SandboxAgent.run_as="pentester"` — is **rejected by the SDK**:
    `Running injected sandbox sessions do not support capability changes to manifest.users/groups`.
  Root cause: the firewall lives *inside the agent's container*, so containment depends on juggling the
  agent's in-container privilege, which fights the SDK at every turn. The correct design (flagged at the
  original S0 review) is enforcement **outside the agent's authority**. See `pm-decision-s0-egress-gateway.md`.
- **The engine has never been launched end-to-end.** Every first-run attempt surfaces a latent
  operational breakage. Bring-up is a debugging chain, not one fix.

---

## Part A — Engine bring-up (get a scan to complete)

**Resolved:** PRE-2 (pydantic strict_mode on inventory tools) — fixed on `main @ d8a6faa`.

**Open #1 — sandbox container exits at startup.** A `STRIX_IMAGE=strix-sandbox:dev` run fails with
`409 Conflict: container not running` inside the SDK's `_ensure_runtime_helpers` — the container's
entrypoint (interactsh + Caido + proxy setup) dies before the keep-alive. Diagnose:
```bash
docker rm -f devtest 2>/dev/null
docker run -d --name devtest strix-sandbox:dev tail -f /dev/null
sleep 8
docker inspect -f 'status={{.State.Status}} exit={{.State.ExitCode}}' devtest
docker logs devtest 2>&1 | tail -30
docker rm -f devtest
```
Fix the failing entrypoint step (likely Caido readiness, a port, or a sudo/cert step). Expect more
latent breakages after this one — work the chain until a scan runs.

**Goal of Part A:** a supervised strix scan against the B-V2P IDOR dev target completes and reports the
IDOR. That proves the engine runs end-to-end (and is the propose-dispose M0 data point later).

---

## Part B — S0-v2: out-of-container egress gateway (the real containment)

**Architecture** (from `pm-decision-s0-egress-gateway.md`):
- Agent container on an **internal Docker network** with **no default internet route**.
- A separate **egress-gateway container** runs the decision proxy and is the **only** path to the
  internet; the agent container's default route points at it.
- Scope is enforced in the **gateway's** network namespace — the agent (root or not, in its own
  container) **cannot reach or flush** the gateway's rules.
- **No `run_as`, no in-container iptables, no create-user juggling** → the entire PRE-3/run_as problem
  class disappears. The agent can run as root harmlessly.

**Remove (retired):**
- `factory.py` `run_as="pentester"` (breaks the engine; unnecessary in S0-v2).
- in-container iptables in `egress-enforcer.sh` / agent-container enforcement.
- the `docker_client.py` `user="root"` exec juggling tied to enforcement.

**Reuse (move into the gateway, keep the logic):**
- `scope.py` `decide()` — the gateway proxy calls it. Unchanged.
- F1 DNS→IP resolved-IP allow-set + rebinding defense (`egress_proxy.py`) — runs in the gateway.
- the Caido `decide()` gate — keep as defence-in-depth (now the agent's egress also can't escape the
  gateway, so this is belt-and-suspenders).
- S3.1 target-health — the gateway sees every connection; feed the breaker from there.

**Wire (`docker_client.py` + a gateway image/compose):**
- Create the agent container on an internal network; create/start the gateway container as the egress
  path; set the agent's routing so all egress traverses the gateway. Keep the existing NET_ADMIN/NET_RAW
  + host-gateway behavior the agent legitimately needs *inside its own netns*.

---

## Order of implementation
1. **Part A bring-up** — engine completes a scan on the dev image (needed to verify anything).
2. **Part B build** — egress-gateway container + internal-network wiring; remove the retired in-container mechanism.
3. **Live containment proof** (this is the gate the operator set): with the gateway active —
   - empty scope ⇒ the agent (run a shell tool, or curl) reaches **nothing** (gateway denies);
   - in-scope host ⇒ reachable;
   - the agent **cannot reach or flush** the gateway's rules (it's a different container);
   - and the engine still completes the scan + reports the IDOR.
4. Full suite green (`uv run pytest tests/ -q`) + `ruff check .` no new errors.

---

## Definition of Done
- [ ] Part A: a supervised scan completes end-to-end on the dev image and reports the B-V2P IDOR.
- [ ] Part B: egress-gateway architecture implemented; in-container iptables + `run_as` removed.
- [ ] Live containment proof (§3) passes: empty-scope agent reaches nothing, in-scope reachable, gateway
      un-flushable from the agent, scan still completes.
- [ ] `decide()` / F1 / Caido-gate / S3.1 reused in the gateway (no logic regression; SP1/SP2/SP3/SP6/SP8 still hold where applicable).
- [ ] Full suite green + ruff clean; completion report per VALIDATION_PROTOCOL §C with pasted evidence
      for bring-up (scan log + IDOR) and containment (empty-scope BLOCKED via the gateway, gateway un-flushable).

## Out of scope / tracked
- **The paper (E1–E4)** does not start until §3 containment is live-proven (operator decision). Once it is,
  E1–E4 run through the same contained engine.
- **PRE-1** — 4 pre-existing bl-fixture full-suite Docker tests — separate track.
- LLM provider routing is the operator's config (`openai/<model>` + `LLM_API_BASE`); not your task.

## Why this is the right teardown, not a loss
SGL's value was never the iptables placement — it was the *decision logic* (scope, ownership, F1,
target-health), which is all kept. The only thing being replaced is *where* enforcement sits, moving it
to a place strix's architecture can actually support. This ends the PRE-3/run_as whack-a-mole and yields
containment that genuinely holds against a root agent. When §3 passes, S0 is real for the first time.
