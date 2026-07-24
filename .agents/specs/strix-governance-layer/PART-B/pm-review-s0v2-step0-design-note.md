# PM Review — S0-v2 Step-0 Design Note

> **From:** PM/Validator (`opus-4.8-pm-auditor`)
> **To:** Producer (coder, CLI)
> **Date:** 2026-06-22
> **Ref:** `Part_B-Step0-Design-Note.md`; `pm-decision-s0-egress-gateway.md`; `coder-handoff-bringup-and-s0v2.md` (Part B §3)
> **Artifact under review:** Step-0 design note, four wiring decisions for the out-of-container egress gateway.

---

## Decision

```
status:   REQUEST-CHANGES
scope:    design-review loopback (NOT a rejection — the architecture is sound)
gating:   blocking items B1–B3 must be resolved in the revised note BEFORE any
          implementation; the in-container enforcer is NOT removed until the
          gateway design is bypass-clean.
```

This is the checkpoint the Step-0 gate exists for. The note is strong work — but it has one internal contradiction and two unaddressed bypass vectors that would each defeat containment against a **root** agent, which is the entire point of S0-v2. Resolve them on paper before we tear out working code.

---

## What is correct — keep it

- `docker network create --internal strix-egress-net` + a **two-NIC gateway** (internal + external) + **agent on the internal NIC only**. Topologically, the agent has no external interface — correct foundation.
- Enforcement on the **gateway's** PREROUTING/FORWARD, in a netns the agent cannot administer (no Docker API, different container). This is the core win, and it holds.
- `scope.decide()`, F1 DNS→IP + rebinding defense, and S3.1 target-health **moved into the gateway with logic unchanged** (reuse, not rewrite). Correct.
- Minimal gateway image (`Dockerfile.gateway`, slim base, governance modules only — no Caido/interactsh/SDK). Correct.
- Teardown list (retire `run_as`, in-container iptables, `user="root"` juggling, agent-side enforce-env) is accurate.

---

## Blocking — must be resolved in the revised note

### B1 · The NET_ADMIN contradiction (Decision 1 vs Decision 4)
Decision 1 sets the agent's default route via `docker exec <agent> ip route add default …`. That syscall requires `CAP_NET_ADMIN` in the agent's netns — which Decision 4 **removes**. As written, route injection fails.

**Required resolution:** set the route with a **host-initiated `docker exec --privileged`**. That grants the capability to *that exec process only*, transiently — the agent's own processes never hold NET_ADMIN, and a root agent cannot manipulate routing. Do **not** leave NET_ADMIN on the container, and do **not** rely on a plain exec. Also gate the agent entrypoint so it performs **no egress before the route is set** (close the start-up window).

### B2 · Gateway FORWARD policy must default-DROP
`STRIX_FILTER` ends with `-A STRIX_FILTER -j ACCEPT`. The agent **keeps NET_RAW** (nmap `-sS`), so a root agent can craft ICMP / raw-IP / arbitrary packets that the PREROUTING TCP+DNS redirect and the non-DNS-UDP drop do not catch. The catch-all ACCEPT would forward them.

**Required resolution:** **FORWARD policy DROP.** Only proxy-mediated, `decide()`'d egress leaves (the proxy opens its *own* upstream connections on the external NIC; those are not agent-forwarded). The final ACCEPT must be scoped to the gateway's own return traffic, never agent-sourced forwarded packets. **This rule is what makes Decision 4's "NET_RAW cannot bypass" claim true** — today that safety depends on a rule the design does not enforce.

### B3 · Confirm the Docker socket is NOT in the agent container
Not addressed in the note. If `/var/run/docker.sock` is mounted in the agent, a root agent uses the Docker API to stop / reconfigure / exec-into the gateway → total bypass, netns isolation notwithstanding.

**Required resolution:** state explicitly that the agent container has **no Docker socket and no Docker API access**.

---

## Important — address in the design or the proof

### I4 · Agent external DNS path
Confirm external name resolution traverses the gateway's F1 enforcer. Docker's embedded resolver (`127.0.0.11`) lives in the agent's netns and may forward to host upstreams **without** crossing the gateway — a DNS-resolution / exfil bypass. Likely fix: override the agent's `resolv.conf` to a resolver reachable **only** via the gateway, and verify embedded-DNS forwarding cannot leak. F1 is only as good as the agent's DNS actually reaching it.

### I5 · IPv6
If Docker assigns IPv6 to these containers, the v4 iptables rules do not cover it and IPv6 egress bypasses everything. **Disable IPv6 on the networks, or mirror every rule in `ip6tables`.**

### I6 · Health transport (Decision 3) — reconsider Option A vs C
Option A opens a host port (a new network surface); the rejection of Option C was "slower / extra API call." But host→gateway `docker exec` is **not** a containment risk — only the *agent* must be unable to reach the gateway; the host legitimately controls it (same trust as today's host→agent exec). **Option C keeps health off the network entirely — prefer it.** If you keep Option A, bind `127.0.0.1` on the host, never `0.0.0.0`.

---

## Minor

### M7 · `egress_proxy.py` "unchanged" is optimistic
As a gateway it now serves non-loopback clients (the agent's IP, not `127.0.0.1`) and intercepts **forwarded** TCP via REDIRECT — it likely needs to bind `0.0.0.0` and read `SO_ORIGINAL_DST` for forwarded connections. A **binding** change is fine; a **decision-logic** change is not — `decide()` and the F1 path must stay byte-identical for gate-neutrality. State which it is.

---

## Live-containment proof — expand §3 to test each vector (agent running as root)

- Empty scope ⇒ agent reaches nothing via **TCP, DNS (name resolution), raw/ICMP (NET_RAW), and IPv6** — not just an HTTP `curl`.
- In-scope host ⇒ reachable.
- Agent **cannot reach the gateway's rules or the Docker socket**; `iptables -F` inside the agent is a no-op / absent.
- Engine still completes the scan + reports the IDOR.

---

## Required next action

1. Revise the design note to **resolve B1–B3** and **address I4–I6** (a short delta is fine — do not rewrite the whole note).
2. Send it back. I confirm the design is bypass-clean, then **green-light implementation**.
3. Teardown of `egress-enforcer.sh` / `run_as` happens **after** the gateway path is designed-clean — we never sit in a state with no containment story.

**Hold-the-line invariants (unchanged):** reuse `decide()` / F1 / S3.1 with decision logic **byte-identical**; SGL is removal-upstream only — never alter a disposition, add an `evidence_class`, or touch any file under `core/logic/`, `core/proposals/`, `core/oob/`, `core/diff/`, `core/race/`.

---

```
Skill: pm-auditor@2.0.0 · validator: opus-4.8-pm-auditor
Reviewed: Part_B-Step0-Design-Note.md (4 decisions)
Findings: 3 blocking (B1 NET_ADMIN contradiction, B2 FORWARD default-DROP, B3 docker socket),
          3 important (I4 DNS path, I5 IPv6, I6 health transport), 1 minor (M7 proxy binding)
Decision: REQUEST-CHANGES — resolve B1–B3 before implementation; teardown after design-clean
Next: producer revises note → PM confirms bypass-clean → green-light build
```
