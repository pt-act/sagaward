# PM Decision — S0 egress enforcement must move OUT of the agent container (S0-v2)

**Author:** opus-4.8-pm-auditor · **Date:** 2026-06-21 · **Status:** REQUIRED for deployment; NOT gating the paper

## Why (three live integration failures of the in-container approach)
1. **PRE-3:** the agent execs as root (SDK uses the container create-user for exec); root is uid-0-exempt from the iptables redirect AND can `iptables -F`.
2. **PRE-4:** packaging — proxy crashed on missing modules (fixed, but symptomatic of fragility).
3. **run_as conflict (this one):** the fix for PRE-3 (`SandboxAgent.run_as="pentester"`) is rejected by the SDK — `Running injected sandbox sessions do not support capability changes to manifest.users/groups` (`runtime_session_manager.py:586`). strix injects a pre-built container; the SDK won't add a user to a running injected session.

Root cause: the firewall lives **inside the agent's container**, so containment depends on juggling the agent's in-container privilege — which fights strix's injected-session SDK model at every turn. This was flagged at the original S0 review ("enforcement must live outside the agent's authority").

## Decision (S0-v2 architecture)
Move egress enforcement to a **separate enforcer/gateway the agent routes through but cannot administer**:
- Agent container on an **internal Docker network** with no default internet route.
- A dedicated **egress-gateway container** (runs the decision proxy) is the only path out; the agent's route points to it.
- Scope enforced in the **gateway's** network namespace — the agent (even as root in its own netns) cannot flush or bypass it.
- **No `run_as` needed** → no SDK injected-session conflict, no agent-user juggling. The agent can run as root harmlessly.

Keep: `scope.py` decision logic, the F1 DNS→IP correlation, the Caido `decide()` gate, S3.1 target-health — all reusable; only the *enforcement substrate location* changes.

## Gate
- **Does NOT gate the paper.** E1–E4 run on owned lab targets with enforcement off (dev image); SGL containment protects against non-owned targets, which the paper does not use.
- **Gates unattended / real-target operation.** The engine must not be run unattended against a non-owned authorized target until S0-v2 lands and its containment is live-proven (pentester-equivalent egress BLOCKED, agent cannot reach the gateway's rules).

## Status of prior S0 work
verdict-10's deterministic test proved the *mechanism* (non-root traffic is redirected); that logic carries into the gateway. The in-container *substrate* (iptables in the agent container + `run_as`) is retired. verdict-10's "containment closed" holds only for the forced-`su` test, not the integrated SDK path — corrected here.

## Immediate action
- Unblock the paper: M0/E1–E4 on `strix-sandbox:dev`, no `STRIX_EGRESS_ENFORCE`.
- Schedule S0-v2 (egress-gateway) as the deployment-readiness item before any unattended real-target run. Producer: Opus (network/containment architecture).
