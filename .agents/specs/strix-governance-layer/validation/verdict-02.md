# Verdict — strix-governance-layer (S0 + S1) — round 2

## Header

```
spec_id:                     strix-governance-layer
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: claude-sonnet-4-6[1m])
reviewed_completion_report:  completion-reportV2.md (round 2)
prior_verdict:               verdict-01.md (needs_revision)
verdict_timestamp:           2026-06-18 23:00 UTC
branch_verified:             sgl-s0-s1 @ b34db7a
```

---

## Decision

```
status: needs_revision
```

**Issue 1 (DNS) is fully resolved** — confirmed by independent trace. The UDP DNS
listener, QNAME parser, NXDOMAIN builder, and upstream forwarder are all present and
fail-closed. One major issue remains on Issue 2: the sudo fix blocks direct bypass
(`sudo iptables`) but leaves indirect bypass (`sudo bash`, `sudo python3`) open.
One minor undeclared change in `scripts/` must be addressed.

---

## Per-Criterion Assessment

### AC-G1 — Production image builds with all pinned tools and egress enforcer active.

- Producer's claim: partially met (authored; build not yet run — unchanged)
- Validator's finding: **unverifiable** (correctly scoped)
- Notes: Issue 1 authored fix is sound. Issue 2 fix is incomplete (see Issues Found). Both must be resolved before the build produces verifiable SP3 results.

---

### AC-G2 — Fail-closed scope: DENY/UNKNOWN/EXPIRED/no-rules blocks.

- Producer's claim: met (S1 unchanged; DNS gap addressed)
- Validator's finding: **confirmed** (S1 decision service, unchanged); DNS enforcement **confirmed via adversarial trace**
- Evidence — validator-constructed DNS fail-closed trace:
  - DNS query arrives → iptables UDP/53 REDIRECT → `_DnsEnforcerProtocol.datagram_received()` → `asyncio.ensure_future(_handle(data, addr))`
  - `_parse_qname(data)`: correctly extracts QNAME from wire format; pointer-loop detection via `visited` set; raises `ValueError` on malformed input → caught by `except Exception` in `_handle()` line 168 → drops without forwarding. Fail-closed on malformed input. ✓
  - No-rules path: `decide(Target(host=domain, action_class=RECON), EngagementCtx(rules=[]))` → `_decide()` line 228 `not ctx.rules` → True → `DENY reason=no_rules` → `_nxdomain_response(data)` → returned to querier. ✓
  - Upstream failure on ALLOW: `_forward_dns()` returns `None` on `OSError/TimeoutError` → `response = _nxdomain_response(data)` (line 189) → fail-closed even when upstream is unreachable. ✓
  - `_nxdomain_response()` flags verified: `0x80 | rd` (QR=1 + RD-copy) in byte 0; `0x83` (RA=1, RCODE=3=NXDOMAIN) in byte 1. RFC-correct. ✓
  - Root exemption: `egress-enforcer.sh` line 114 `--uid-owner 0 -j RETURN` before the TCP REDIRECT rule. `_forward_dns()` runs as root (uid 0); its UDP packets bypass REDIRECT and go directly to `_DNS_UPSTREAM`. No loop. ✓
  - UDP socket binding: `socket.AF_INET, SOCK_DGRAM` bound to `127.0.0.1:48081` in `_main()` lines 311–317, alongside the TCP server on the same port number. TCP and UDP are independent socket namespaces; this is correct. ✓

---

### AC-G3 through AC-G7

- Validator's finding: **confirmed not met** (correctly scoped S2–S6, unchanged)

---

### AC-G8 — Gate-neutral.

- Validator's finding: **confirmed** (unchanged; import boundary verified in round 1, no new engine imports in round 2 delta)

---

### AC-G9 — Audit: every allow/deny/halt decision logged.

- Validator's finding: **confirmed partial** (unchanged; DNS handler logs at `_handle()` line 180–183, TCP handler unchanged)

---

### Non-functional — Fail-closed on error path.

- Validator's finding: **confirmed** (DNS parse error → drop; upstream failure → NXDOMAIN; TCP SO_ORIGINAL_DST failure → close; all confirmed)

---

## Issues Found

**Issue 2 residual (major) — sudo restriction is a blocklist; indirect bypass via root shell is not closed**

- Location: `containers/Dockerfile.prod` — `sed` sudoers patch
- Description: The fix uses a sudoers **blocklist**: `NOPASSWD:ALL, !iptables, !ip6tables, !nft, …`. This blocks `sudo iptables` directly. It does **not** block `sudo bash`, `sudo sh`, `sudo python3`, or any other general-purpose interpreter/shell. From a process running as root (obtained via `sudo bash`), iptables needs no sudo — the restriction is bypassed entirely. Validator-constructed bypass: `sudo bash -c 'iptables -t nat -F'` — `bash` is not in the exclusion list, so this succeeds and flushes all SGL enforcement rules. The SP3 adversarial test as written tests only the direct form (`sudo iptables -t nat -F`) and would pass while the indirect bypass remains open.
- Suggested remedy (two options, either resolves the issue):
  - **Option A (recommended — allowlist):** Replace `NOPASSWD:ALL, !…` with an explicit allowlist of only the commands pentester legitimately needs (e.g., `NOPASSWD: /usr/bin/nmap, /usr/sbin/naabu, …`). Allowlists are the correct tool; blocklists are incomplete by construction.
  - **Option B (simplest):** Revoke sudo entirely for pentester in the prod stage (`RUN sed -i '/pentester.*ALL/d' /etc/sudoers && visudo -c`). Then grant only specific required capabilities via `setcap` on the binaries that need them (nmap already has `cap_net_raw` in the base image). No sudo, no bypass path.
  - In either case, **update the SP3 test** to include the indirect form: `sudo bash -c 'iptables -t nat -F' && curl https://example.com && echo BYPASS || echo BLOCKED` — Expected: `sudo bash` denied or iptables fails.

**Issue 3 (minor) — Undeclared executable-bit change on `scripts/`**

- Location: `scripts/build.sh`, `scripts/docker.sh`, `scripts/install.sh`
- Description: `git diff origin/main --name-only` shows these three files changed from mode 100755 to 100644 (executable bit dropped). They are not listed in Artifacts Produced and no change was intended. These scripts being non-executable breaks `./scripts/docker.sh` invocation. This is likely a git checkout or filesystem artefact from the producer's environment.
- Suggested remedy: `git checkout origin/main -- scripts/build.sh scripts/docker.sh scripts/install.sh` (or `git update-index --chmod=+x scripts/*.sh`) and amend or add a fix commit.

---

## What changed from round 1 — validation confirmation

**Issue 1 (DNS enforcement gap): RESOLVED.** The DNS enforcement gap identified in verdict-01.md is fully closed. `_DnsEnforcerProtocol` is a real `asyncio.DatagramProtocol` with a UDP listener on the same port as the TCP proxy. It calls `decide()` per query, returns NXDOMAIN on DENY, forwards on ALLOW via the root-exempt `_forward_dns()`, and is fail-closed on every error path. The `contextlib` import is now top-level. Root exemption (`uid-owner 0`) is correctly motivated and documented.

**Issue 2 (sudo restriction): PARTIALLY RESOLVED.** The direct bypass (`sudo iptables`) is now blocked by the sudoers negation. The indirect bypass via a root shell (e.g., `sudo bash`) remains open. The fix is structurally correct in approach (modifying the sudoers rule, verifying with `visudo -c`) but incomplete because blocklist negation cannot enumerate all paths to privilege escalation.

---

## Verdict Rationale

Issue 1 is clean — the DNS fix is architecturally correct, fail-closed on every traced path, and properly handles the root-exemption loop concern. The S1 decision service remains sound and unchanged. The outstanding revision is narrow: one major (Issue 2 sudo residual — indirect bypass not closed) and one minor (scripts executable bit). Both are fixable in the authored files before the build. The major finding directly affects the validity of SP3: if the adversarial test does not include the indirect bypass attempt, the build will appear to pass SP3 while remaining bypassable. Fixing Issue 2 before the build is cheaper than discovering it after.

---

## Session Manifest

```
Skill: pm-auditor@2.0.0 + validation-upgrade-adversarial-semantics (v2.1)
Interpreter: opus-4.8-pm-auditor
Role: validator
Spec: strix-governance-layer (S0+S1)
Validation round: 2
Branch: sgl-s0-s1 @ b34db7a
Files read: strix/runtime/egress_proxy.py (full, round 2), containers/Dockerfile.prod
            (sudo block grep), containers/egress-enforcer.sh (uid-owner grep),
            scripts/ diff vs main
Criteria verified: 7 confirmed (S1 unchanged + DNS trace), 0 refuted, 2 unverifiable (AC-G1 build; SP8 runtime)
Decision: needs_revision
Issues: 1 major (Issue 2 sudo residual), 1 minor (scripts executable bit)
Prior conflict: no
Self-check result: passed — adversarial direction checked (v2.1) on both fixes
Drift observed: no
Escalations: none
```
