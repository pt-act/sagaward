# Step-0 Design Note — S0-v2 Out-of-Container Egress Gateway (Revised)

**From:** Producer (Qwen/Opus routing)
**Date:** 2026-06-22 (revised after PM review)
**Ref:** pm-review-s0v2-step0-design-note.md; pm-decision-s0-egress-gateway.md; Part-B-Kickoff.md
**Purpose:** Four riskiest wiring decisions for the out-of-container egress gateway, revised to resolve B1–B3 (blocking), I4–I6 (important), M7 (minor).

---

## Decision 1: Internal Network + Agent Container Routing

**Current state:** No custom Docker network. Agent container on the default bridge with `extra_hosts={"host.docker.internal": "host-gateway"}` for host access. All egress goes direct.

**Proposed:**

```
docker network create --internal strix-egress-net
```

`--internal` creates a network with **no default route to the internet** — containers on it can reach each other but nothing outside. The gateway container gets **two** network interfaces:

1. `strix-egress-net` (internal) — receives agent traffic.
2. Default bridge (or a second explicit external network) — provides internet egress.

The agent container gets **one** interface: `strix-egress-net` only. It has no route to anything except the gateway and other containers on the same internal network.

### AMENDMENT B1 — Route injection via transient privileged exec (not in-container NET_ADMIN)

**Original text used `docker exec <agent> ip route add default …`, which requires `CAP_NET_ADMIN` in the agent's netns — contradicting Decision 4 which removes it.**

**Revised mechanism:** The host sets the route with a **transient** `docker exec --privileged`:

```bash
docker exec --privileged <agent> ip route add default via <gateway-ip-on-internal-net>
```

`--privileged` grants `CAP_NET_ADMIN` to **that exec process only**, transiently — it exits after the route is set. The agent's own processes never hold NET_ADMIN; the container's capability bounding set omits it, so even a root agent inside cannot re-acquire NET_ADMIN (bounding sets cannot be expanded from inside a container).

**Startup race gate:** The agent's entrypoint must perform **no egress before the route is set**. Implementation: the host injects a startup guard via `docker exec` that writes a sentinel file (e.g. `/var/run/strix-route-set`) after route injection. The agent entrypoint blocks on the existence of this file before opening any outbound connection. This closes the window where the agent might attempt egress via Docker's embedded DNS (see I4) or direct TCP before the gateway is in the decision path.

**Lifecycle:** Create network → create gateway → read gateway IP → create agent → `docker exec --privileged` route injection → write sentinel → agent entrypoint unblocks.

### AMENDMENT I4 — Agent external DNS path must traverse gateway

**Docker's embedded DNS resolver (`127.0.0.11`) lives in the agent's netns and forwards external queries via the container's network stack. On the current proposal, those forwarded queries would traverse the gateway (following the default route) — but relying on this is fragile: Docker's resolver implementation could change, and the embedded resolver also resolves container names locally (no gateway decision).**

**Resolution:** Override the agent container's `/etc/resolv.conf` to point directly to the gateway's IP on `strix-egress-net`:

```
nameserver <gateway-ip-on-internal-net>
```

This is injected via `docker exec` (same transient-privileged session as the route injection). All DNS queries — external and internal — now go directly to the gateway's F1 DNS enforcer (port 53 → iptables REDIRECT → 48081). Docker's embedded resolver (`127.0.0.11`) is never consulted. No DNS resolution/exfil bypass exists.

**Verification:** After override, `dig @127.0.0.11` from inside the agent must fail or return NXDOMAIN for external names, confirming the embedded resolver is out of the decision path.

The `extra_hosts` injection for `host.docker.internal` stays in the **gateway** container (not the agent). The gateway resolves `host.docker.internal` → host-gateway on its external interface, and `decide()` governs whether the agent can reach it.

**`host.docker.internal` in the agent container:** Removed. The agent no longer needs a direct host mapping — all egress (including to the host) routes through the gateway. The gateway has `extra_hosts={"host.docker.internal": "host-gateway"}` on its external network, so it can forward to the host when `decide()` allows.

**Network creation lifecycle:** `docker_client.py` creates the network before creating either container, records the network ID, and tears it down on session deletion. The gateway container is created first (so its IP is known), then the agent container is created and connected.

### AMENDMENT B3 — Agent container has no Docker socket or Docker API access

The agent container is created with **no mount of `/var/run/docker.sock`**, no Docker CLI binary, and no volume that provides Docker API access. This is already the case in the current `docker_client.py` (no socket mount exists), but it must be stated as an **explicit design invariant**: a root agent inside the container cannot use the Docker API to stop, reconfigure, or exec-into the gateway. The gateway's isolation depends on this — without it, a root agent could reconfigure the gateway container and bypass all containment.

**Verification:** `docker inspect <agent> | jq '.Mounts'` must show no docker.sock mount. This is checked in the live-containment proof.

---

## Decision 2: Gateway Enforcement in Its Own netns

**Current state:** iptables rules in the `OUTPUT` chain of the **agent** container. Traffic from the same container is `REDIRECT`ed to the local proxy. Root (uid 0) and strix-proxy (uid 9999) are exempt via `uid-owner RETURN`. The agent as root can `iptables -F` (PRE-3).

**Proposed:** The iptables rules move to the **FORWARD** chain of the **gateway** container. No in-container OUTPUT redirect. The gateway enforces cross-container traffic:

### AMENDMENT B2 — FORWARD policy DROP, catch-all scoped to return traffic only

**Original text had `-A STRIX_FILTER -j ACCEPT` as catch-all, which would forward agent-sourced raw/ICMP/IPv6 packets that the TCP+DNS redirect and UDP drop do not catch. A root agent with NET_RAW can craft these.**

**Revised iptables (complete rule set):**

```bash
# ─── Gateway container iptables ───

# Default policy: DROP everything forwarded through this container
iptables -P FORWARD DROP

# nat table — redirect agent traffic to the decision proxy on the gateway
iptables -t nat -N STRIX_EGRESS
iptables -t nat -A STRIX_EGRESS -s <agent-ip> -p udp --dport 53 -j REDIRECT --to-ports 48081
iptables -t nat -A STRIX_EGRESS -s <agent-ip> -p tcp -j REDIRECT --to-ports 48081
iptables -t nat -A PREROUTING -i <internal-net-interface> -j STRIX_EGRESS

# filter table — only proxy-mediated, decide()'d egress leaves the gateway
iptables -N STRIX_FILTER
# DNS UDP from agent → allowed (redirected to F1 enforcer by nat rule above)
iptables -A STRIX_FILTER -s <agent-ip> -p udp --dport 53 -j ACCEPT
# Non-DNS UDP from agent → DROP (no nmap UDP scan bypass)
iptables -A STRIX_FILTER -s <agent-ip> -p udp -j DROP
# ESTABLISHED,RELATED return traffic for proxy-initiated upstream connections
iptables -A STRIX_FILTER -m state --state ESTABLISHED,RELATED -j ACCEPT
# Gateway's own outbound on the external interface (not forwarded, not matched)
# Nothing else. No catch-all ACCEPT for agent-sourced forwarded packets.
iptables -A FORWARD -j STRIX_FILTER

# Loopback on the gateway itself — always allowed
iptables -A FORWARD -i lo -j ACCEPT
```

**Why the catch-all ACCEPT is gone:** The proxy opens **its own** upstream connections on the gateway's external interface. Those are locally-originated (OUTPUT chain), not forwarded — they never hit FORWARD. The only traffic that traverses FORWARD is agent→gateway→upstream, and only TCP/DNS that was REDIRECTed to the proxy. ESTABLISHED,RELATED covers the return packets for proxy-initiated connections. Any agent-sourced packet that isn't TCP or DNS UDP is caught by the default DROP policy or the explicit UDP DROP rule.

**NET_RAW cannot bypass this:** Even with NET_RAW, a root agent can craft ICMP, raw-IP, or arbitrary packets — but they all arrive on the gateway's internal interface, enter the FORWARD chain, and hit the default DROP policy (no matching rule = DROP). The only packets that get forwarded are those the proxy explicitly decided to allow.

**Agent cannot flush gateway's rules:** The agent has no access to the gateway container. It can't `docker exec` into it (no Docker API, per B3), can't reach its iptables (different netns), can't reach its management interfaces. Even if the agent runs as root in its own container, it is root **only within its own netns** — which has no iptables enforcement rules.

### AMENDMENT I5 — IPv6 disabled on both networks

Docker may assign IPv6 addresses to containers on custom networks. The v4 iptables rules above do not cover IPv6 egress — an IPv6 path would bypass everything.

**Resolution:** Disable IPv6 on both `strix-egress-net` and the external network:

```bash
# At network creation
docker network create --internal --ipv6=false strix-egress-net
docker network create --ipv6=false strix-external-net
```

If `--ipv6=false` is not a supported Docker flag (it is not in current Docker versions), the alternative is to disable IPv6 inside each container via sysctl:

```bash
docker exec <gateway> sysctl -w net.ipv6.conf.all.disable_ipv6=1
docker exec <agent> sysctl -w net.ipv6.conf.all.disable_ipv6=1
docker exec <gateway> sysctl -w net.ipv6.conf.default.disable_ipv6=1
docker exec <agent> sysctl -w net.ipv6.conf.default.disable_ipv6=1
```

These sysctl settings are injected during the transient-privileged setup session (same as route injection). The agent cannot re-enable IPv6 because it lacks `CAP_NET_ADMIN`.

**If IPv6 must be supported in future:** mirror every v4 iptables rule in `ip6tables` with the same logic. This is not done now — IPv6 is explicitly disabled.

### AMENDMENT M7 — egress_proxy.py binding change vs logic change

In gateway mode, the proxy serves non-loopback clients (the agent container's IP on `strix-egress-net`) and intercepts **forwarded** TCP via iptables REDIRECT. This requires:

- **Binding change:** TCP listener and DNS enforcer change from `127.0.0.1` to `0.0.0.0` (to accept connections arriving on the internal network interface). The port stays 48081.
- **SO_ORIGINAL_DST:** Already implemented and used for TCP; works unchanged for forwarded connections (REDIRECT in PREROUTING sets the original dst, `getsockopt(SO_ORIGINAL_DST)` retrieves it the same way).
- **Decision logic:** `decide()` and the F1 DNS enforcer path are **byte-identical** — no logic changes. The only code change is the bind address string (`"127.0.0.1"` → `"0.0.0.0"`), which is a deployment/binding concern, not a decision-logic concern.

**Gateway image:** A minimal image (not the full Kali dev image). Based on `python:3.12-slim` or similar, with only iptables + the governance Python modules (scope.py, egress_proxy.py, breaker.py, etc.) + pydantic. No Caido, no interactsh, no security tools, no agent SDK. The Dockerfile is a new `containers/Dockerfile.gateway`.

**Gateway startup:** Entrypoint is a new `gateway-entrypoint.sh` that:
1. Sets up iptables rules (PREROUTING/FORWARD chains, default DROP policy).
2. Disables IPv6 via sysctl.
3. Starts `python3 -m strix.runtime.egress_proxy --bind 0.0.0.0` with `STRIX_SCOPE_RULES` and `STRIX_EGRESS_ENFORCE=1` in its env.
4. Waits for proxy readiness (Unix-domain health socket check).
5. Signals readiness to the host orchestrator.

---

## Decision 3: Where decide(), F1, Caido gate, and S3.1 Run Inside the Gateway

**scope.py decide():** Runs inside the **gateway** container, called by `egress_proxy.py` on every TCP/DNS decision. The `STRIX_SCOPE_RULES` env var is injected into the gateway container at creation time (not the agent container). `scope.py` is installed in the gateway's Python path (same targeted-COPY approach as the current prod image, into `/opt/strix-python/strix/`). Logic is **byte-identical** — reuse, not rewrite. Confirmed: scope.py has zero strix imports, no LLM, only pydantic + stdlib.

**F1 DNS→IP + rebinding defense:** Runs inside the **gateway**. The proxy's `_DnsEnforcerProtocol` intercepts DNS queries from the agent, resolves upstream, adds A/AAAA records to `_resolved_ips`, and defends against rebinding via `_is_internal_ip` / `_is_ip_in_scope`. Logic **byte-identical**. DNS queries now come from the agent's IP on `strix-egress-net` (not 127.0.0.1), and the listener binds `0.0.0.0` (M7). The DNS enforcer's upstream resolver (default 8.8.8.8) uses the gateway's external interface — out of the agent's reach.

**Caido decide() gate:** Caido runs **inside the agent container** on loopback (`127.0.0.1:48080`). Caido's outbound connections follow the agent's default route — which now goes to the gateway. So Caido traffic is subject to `decide()` like everything else. No special Caido bypass in the gateway.

**S3.1 target-health recording:** Runs inside the **gateway**. The proxy records connection outcomes to `/var/log/strix/target_health.jsonl`.

### AMENDMENT I6 — Health transport: Option C (docker exec from host)

**Original note proposed Option A (host-facing HTTP API on port 48082). PM review: Option A opens a new network surface; Option C (docker exec) keeps health off the network entirely. The agent must not reach the gateway — but the host legitimately controls it (same trust boundary as today's host→agent exec).**

**Revised:** The host reads target-health events via `docker exec <gateway> cat /var/log/strix/target_health.jsonl`. This is the same mechanism as today (host→container exec), just targeting the gateway instead of the agent. No new host port, no HTTP endpoint, no shared volume.

The existing health Unix-domain socket (`/run/strix/decision.sock`) stays for the **host orchestrator's liveness check** during startup — the host verifies the proxy is ready by exec'ing into the gateway and checking the socket. This is already the current mechanism.

**Why this is safe:** The agent has no Docker API access (B3), so it cannot exec into the gateway. The host→gateway docker exec crosses a trust boundary that the agent cannot cross.

---

## Decision 4: NET_ADMIN/NET_RAW in the Agent's Own netns

**Current state:** `cap_add=["NET_ADMIN", "NET_RAW"]` on the agent container. NET_ADMIN was needed for iptables (now retired). NET_RAW is needed for nmap SYN scan (`-sS`) which uses raw sockets.

**Proposed:**

- **NET_ADMIN: Removed** from the agent container. The agent's capability bounding set omits NET_ADMIN. Route injection (B1) uses a transient `docker exec --privileged` from the host — the agent's own processes never hold it. Even a root agent cannot re-acquire NET_ADMIN (bounding sets cannot expand from inside). IPv6 sysctl disable (I5) also uses the transient privileged exec.
- **NET_RAW: Kept** on the agent container. nmap's `-sS` (TCP SYN scan) requires `CAP_NET_RAW` for raw socket construction. NET_RAW gives the agent raw-socket power **within its own netns**, but the packets still traverse the gateway, which enforces scope via FORWARD DROP policy (B2). The agent can't use NET_RAW to bypass the gateway because:
  1. All packets leaving the agent's interface arrive on the gateway's internal interface.
  2. They enter the FORWARD chain with default DROP policy.
  3. Only TCP/DNS UDP that is REDIRECTed to the proxy and `decide()`'d gets forwarded.
  4. ICMP, raw-IP, and arbitrary crafted packets hit the default DROP — no matching rule.

**SYS_ADMIN / FUSE:** Stays as-is (conditional, per manifest) — unrelated to enforcement.

**host-gateway behavior:** The agent no longer has `extra_hosts={"host.docker.internal": "host-gateway"}`. Host access routes through the gateway, which has the host-gateway mapping. The agent can reach `host.docker.internal` only when `decide()` allows.

---

## Live-Containment Proof — Expanded (per PM review §3)

All tests run with the agent container running as **root** (worst case).

1. **Empty scope ⇒ agent reaches nothing via TCP, DNS, raw/ICMP, and IPv6:**
   - `curl http://external-site` → gateway PREROUTING REDIRECT → proxy → `decide()` DENY → 403.
   - `dig external-site.com @<gateway-ip>` → gateway DNS enforcer → `decide()` DENY → NXDOMAIN or DROP.
   - `ping external-site` → ICMP packet arrives at gateway → FORWARD DROP (no matching rule).
   - `nmap -sU external-site` → non-DNS UDP → STRIX_FILTER DROP.
   - IPv6 disabled (I5) → no IPv6 egress path.

2. **In-scope host ⇒ reachable:**
   - `curl http://host.docker.internal:9080` → gateway REDIRECT → proxy → `decide()` ALLOW → host.docker.internal resolved by gateway → upstream connection → response relayed.
   - `dig target.local @<gateway-ip>` → DNS enforcer → ALLOW → A record returned.

3. **Agent cannot reach gateway rules or Docker socket:**
   - `iptables -F` inside agent → no iptables in agent's netns (none installed, no NET_ADMIN to add them).
   - `docker stop <gateway>` → no Docker socket/API in agent container (B3).
   - `docker exec <gateway> …` → no Docker API access (B3).

4. **Engine completes scan + reports IDOR:**
   - Full M0-style scan (agent, tools, harness, breaker) completes on the B-V2P target via the gateway.
   - IDOR finding reported as before — no functional regression.

---

## Summary: What Is Removed, What Is Reused, What Is New

| Item | Action | Location | PM finding addressed |
|---|---|---|---|
| iptables OUTPUT redirect (egress-enforcer.sh) | **Removed** | Was: agent container | — |
| uid-owner exemptions | **Removed** | Was: agent iptables | — |
| `run_as="pentester"` / `user="root"` create_kwargs | **Removed** | Was: docker_client.py | — |
| `STRIX_EGRESS_ENFORCE` / `STRIX_SCOPE_RULES` env injection into agent | **Removed** | Was: docker_client.py | — |
| `NET_ADMIN` cap_add on agent | **Removed** | Was: docker_client.py | B1 |
| `host.docker.internal` extra_host on agent | **Removed** | Was: docker_client.py | — |
| Docker socket mount on agent | **Never present — now explicit invariant** | docker_client.py | B3 |
| Docker embedded DNS resolver (127.0.0.11) | **Disabled** (resolv.conf override) | agent container | I4 |
| IPv6 on container networks | **Disabled** (sysctl) | agent + gateway containers | I5 |
| FORWARD catch-all ACCEPT | **Removed** → default DROP + ESTABLISHED,RELATED | Was: gateway iptables | B2 |
| Health HTTP API (Option A) | **Not built** — use Option C (docker exec) | host → gateway | I6 |
| scope.py `decide()` | **Reused** (byte-identical) | gateway container | — |
| F1 DNS→IP + rebinding defense | **Reused** (byte-identical, bind change only) | gateway container | M7 |
| egress_proxy.py TCP+DNS proxy | **Reused** (byte-identical, bind change only) | gateway container | M7 |
| S3.1 target-health recording | **Reused** (docker exec read, same mechanism) | gateway container | I6 |
| Caido decide() gate (belt-and-suspenders) | **Reused** (implicit: outbound → gateway) | agent container | — |
| Internal Docker network creation | **New** | docker_client.py | — |
| Gateway container creation + lifecycle | **New** | docker_client.py / backends.py | — |
| Gateway iptables (FORWARD DROP + PREROUTING REDIRECT) | **New** | gateway-entrypoint.sh | B2 |
| Gateway Dockerfile | **New** | containers/Dockerfile.gateway | — |
| Agent default-route injection (transient --privileged exec) | **New** | docker_client.py | B1 |
| Agent entrypoint egress gate (sentinel file) | **New** | agent entrypoint | B1 |
| Agent resolv.conf override (gateway DNS) | **New** | docker_client.py (exec) | I4 |
| IPv6 sysctl disable | **New** | docker_client.py (exec) | I5 |
