# S0 Authored Artifacts Report — Production Sandbox Image + Egress-Enforcement Substrate

**Date:** 2026-06-18
**Status:** AUTHORED — awaiting operator build + SP3 adversarial test
**Deliverable files:**

| File | Purpose |
|------|---------|
| `containers/Dockerfile.prod` | Multi-stage prod build extending the dev image |
| `containers/docker-entrypoint.prod.sh` | Prod entrypoint — calls enforcer then delegates |
| `containers/egress-enforcer.sh` | iptables/proxy substrate installer |
| `strix/runtime/egress_proxy.py` | In-container transparent decision proxy |
| `strix/runtime/docker_client.py` | Updated — injects SGL env vars on container create |

---

## Architecture (what was authored and why)

### Design choice: iptables REDIRECT + transparent proxy

The spec's central requirement is *egress completeness* — all traffic (HTTP, raw sockets,
DNS, browser, shelled-out nmap/curl/sqlmap) must pass a `decide()` call.  App-layer hooks
alone (Caido, Python middleware) cannot satisfy this because the agent shells out tools that
open their own sockets.

The chosen architecture:

```
pentester process (nmap / curl / browser / Caido)
    │
    │ TCP/UDP outbound
    ▼
iptables REDIRECT (nat OUTPUT chain)  ← blocks / redirects to strix-proxy uid
    │
    ▼
strix.runtime.egress_proxy (127.0.0.1:48081)
    │
    │ decide(Target, ctx) — pure Python, deterministic
    ▼
strix.core.govern.scope.decide()
    │
    ├── DENY → TCP RST / HTTP 403 returned to tool; connection dropped
    └── ALLOW → forward to original dst (SO_ORIGINAL_DST recovery)
```

**Key properties:**
- Default-deny: iptables OUTPUT policy is DROP for non-loopback after rules are installed.
- Proxy's own traffic is exempt via `--uid-owner 9999` (strix-proxy user) so it doesn't loop.
- DNS (UDP 53) is also redirected to the proxy, so DNS resolution for out-of-scope hosts is
  blocked before any TCP connection is attempted.
- Loopback is always allowed (Caido on 127.0.0.1:48080, interactsh sidecar, health checks).
- `STRIX_EGRESS_ENFORCE=0` (or absent) → enforcer script is skipped; dev image behaviour
  preserved.

### `containers/egress-enforcer.sh`

Run as root inside the container at startup.  Steps:
1. Start `strix.runtime.egress_proxy` (Python, runs as strix-proxy uid).
2. Wait for the proxy to be ready (socket/port check, 10 s timeout).
3. Install iptables REDIRECT rules (nat OUTPUT).
4. Install iptables DROP policy for raw UDP non-DNS.
5. Verify the proxy is still alive after rule installation.

### `strix/runtime/egress_proxy.py`

Transparent asyncio TCP proxy.  For each accepted connection:
1. Recovers the pre-REDIRECT destination via `SO_ORIGINAL_DST`.
2. Classifies `ActionClass` from destination port (heuristic; conservative → HTTP).
3. Calls `strix.core.govern.scope.decide(target, ctx)`.
4. DENY → writes HTTP 403 and closes. ALLOW → opens connection to original dst and pipes.

Scope context is loaded from `STRIX_SCOPE_RULES` env at startup and reloaded on SIGHUP.

### `containers/Dockerfile.prod`

Multi-stage build:
- `dev` stage: the existing `Dockerfile` (base image alias).
- `prod` stage: installs iptables/nftables explicitly, creates `strix-proxy` uid (9999),
  copies `egress-enforcer.sh` and the prod entrypoint.

Build command:
```bash
docker build -f containers/Dockerfile.prod --target prod -t strix-sandbox:prod .
```

### `strix/runtime/docker_client.py` (delta)

When `STRIX_EGRESS_ENFORCE=1` is set on the host:
- Injects `STRIX_EGRESS_ENFORCE=1` and `STRIX_SCOPE_RULES` into the container environment.
- `NET_ADMIN` and `NET_RAW` caps were already added (for nmap); they are also required by
  the iptables enforcer.  No cap change needed.

---

## SP3 Adversarial Test — Operator's Responsibility

**SP3 (egress completeness): no egress path bypasses the enforcer.**

The operator must run the following after building the prod image:

### Step 1 — Verify default-deny (no rules → all blocked)

```bash
docker run --rm \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 \
  -e STRIX_SCOPE_RULES="" \
  strix-sandbox:prod bash -c '
    echo "=== curl test ===" && \
    curl -s --max-time 5 https://example.com && echo "BYPASS" || echo "BLOCKED"; \
    echo "=== nmap test ===" && \
    nmap -sT -p80 --open --max-retries 0 example.com 2>&1 | grep -E "BYPASS|filtered|closed|failed" || echo "BLOCKED"; \
    echo "=== DNS test ===" && \
    dig @8.8.8.8 +time=3 +tries=1 example.com 2>&1 | grep -E "BYPASS|timed out|connection timed" || echo "BLOCKED"
  '
```

**Expected:** all three print `BLOCKED`.

### Step 2 — Verify ALLOW path works (scope rule present)

```bash
docker run --rm \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 \
  -e STRIX_SCOPE_RULES="example.com" \
  strix-sandbox:prod bash -c 'curl -s https://example.com | head -1'
```

**Expected:** HTML response from example.com (not a timeout or 403).

### Step 3 — Out-of-scope host blocked when another host is in scope

```bash
docker run --rm \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 \
  -e STRIX_SCOPE_RULES="allowed-target.internal" \
  strix-sandbox:prod bash -c '
    curl -s --max-time 5 https://example.com && echo "BYPASS" || echo "BLOCKED"
  '
```

**Expected:** `BLOCKED`.

### Step 4 — Shell-spawned tools (sqlmap / nuclei) are also gated

```bash
docker run --rm \
  --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 \
  -e STRIX_SCOPE_RULES="" \
  strix-sandbox:prod bash -c '
    sqlmap -u "http://example.com/page?id=1" --batch --timeout 5 2>&1 | tail -5
  '
```

**Expected:** sqlmap fails to reach example.com (connection error / timeout, not a finding).

These four outcomes constitute Gate-4 / SP3 evidence.  Record the before/after output and
attach to this report.

---

## What Is NOT Done Here

- The running image and SP3 pass/fail evidence — operator build step.
- Ownership attribution (S2) — `decide()` in the proxy currently uses the base
  `EngagementCtx`; ownership confidence is a S2 addition to the scope rules.
- Rate/cred limiter (S2) — not wired into the proxy yet.
- Circuit-breaker integration (S3).
- Caido HTTP-path routing through `decide()` (S7).
