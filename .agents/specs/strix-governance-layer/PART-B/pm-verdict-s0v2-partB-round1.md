# PM Verdict — Part B (S0-v2 Egress Gateway), Round 1

> **From:** PM/Validator (`opus-4.8-pm-auditor`)
> **To:** Producer (coder, CLI)
> **Date:** 2026-06-22
> **Ref:** Part B implementation report; `pm-verdict-s0v2-step0-design-rev2.md`; `coder-handoff-bringup-and-s0v2.md` §3; ARCH #11
> **Reviewed:** implementation summary + the partial live-containment proof.

---

## Decision

```
status:  NEEDS-REVISION (Part B in_progress — NOT approved)
reason:  the live-containment proof FAILS on its core criterion — cross-namespace
         TCP interception does not work with REDIRECT. Containment is not proven.
gate:    E1 / the paper REMAIN BLOCKED. The operator's hard gate is exactly this proof.
```

This is the right kind of "not done." You built the architecture, validated the agent-side hardening, and — most importantly — **surfaced the REDIRECT/TPROXY limitation honestly instead of dressing up a passing proof.** That is the §01 "real progress only" discipline working as intended. The verdict below is about closing the gap, not about the integrity of the report.

---

## What is genuinely validated (keep it)

| Check | Status | Confirms |
|---|---|---|
| Gateway boots, proxy listens, iptables install | ✅ | gateway image + entrypoint |
| Agent **cannot** run iptables (permission denied) | ✅ | NET_ADMIN removed from agent (B1/Decision 4) |
| Direct proxy connection ⇒ 403 with empty scope | ✅ | `decide()` runs in the gateway, fail-closed (when traffic reaches it) |
| Route + `resolv.conf` injection into agent | ✅ | B1 transient-privileged wiring, I4 resolv override |

The agent-side hardening holds. The decision logic works *when traffic reaches the proxy*. The wiring lands.

---

## The blocker — and the diagnosis is correct

`iptables REDIRECT` performs a DNAT to the gateway's **local** proxy. Across network namespaces the client's TCP stack rejects the SYN-ACK because its source IP (the gateway/proxy) ≠ the original destination IP the client connected to. REDIRECT is for same-host/same-netns transparent proxying; a **gateway intercepting forwarded traffic from another netns requires TPROXY (`IP_TRANSPARENT`)**, which delivers to a local socket *without* rewriting the destination, so the return path is correct.

Your follow-up #1 names exactly the right fix. Net effect today: the agent's TCP can't complete to anything — which is fail-*closed* (safe), but the engine also can't reach in-scope targets, so the gateway is currently a wall, not a governed path. Both "in-scope reachable" and "engine completes the scan" fail. **Not proven.**

**One hard constraint on the fix:** the transparent path must stay *transparent*. Do **not** substitute an explicit `http_proxy`/SOCKS configuration as a shortcut — the agent shells out (nmap/sqlmap/curl) and uses raw sockets (`-sS`), which don't honor proxy env. That reintroduces the exact shell-tool bypass that motivated the container-boundary design (ARCH #11). TPROXY is required, not optional.

---

## Required to close Part B

1. **Implement TPROXY for TCP interception.**
   - `gateway-entrypoint.sh`: mangle-table `TPROXY` target + fwmark + policy routing (`ip rule add fwmark … lookup N` / `ip route add local 0.0.0.0/0 dev lo table N`), replacing the nat PREROUTING REDIRECT for TCP.
   - `egress_proxy.py`: set `IP_TRANSPARENT` on the listener; retrieve the original destination from the accepted socket (TPROXY preserves dst — `getsockname`), replacing the `SO_ORIGINAL_DST` path. The gateway has `NET_ADMIN`, so the transparent socket is permitted there.
   - **`decide()` and the F1 DNS-enforcement logic stay BYTE-IDENTICAL.** Swapping REDIRECT→TPROXY is *interception plumbing*, which is allowed under the binding-not-logic rule — but the scope-decision and rebinding-defense code must not change. State explicitly which lines are plumbing vs. logic.

2. **Confirm the DNS path still intercepts.** The agent's `resolv.conf` points at the gateway IP, so DNS is addressed *directly to the gateway* (local delivery, not forwarded) — it should not have the cross-netns problem and a local `:53`→`:48081` handling should work. Verify it does after the TPROXY change.

3. **Re-run the FULL live-containment proof and pass every criterion** (agent as **root**): empty-scope blocked via **TCP / DNS / raw-ICMP / IPv6 / the `127.0.0.11` adversarial case (Condition 1)**; **in-scope reachable** (now actually testable once TPROXY lands); agent can't reach the gateway rules or the Docker socket; **engine completes the scan + reports the IDOR**. Paste the evidence per criterion.

4. **Prove the 4 test failures are PRE-1, not a regression.** You just refactored Docker networking in `docker_client.py`. "Connection refused" in the `test_business_logic_fixture` tests could be the pre-existing PRE-1 *or* a side effect of the new internal-network wiring breaking fixture connectivity. **Confirm the same 4 tests fail identically on the base commit before your changes** — establish they're PRE-1, not induced by the network refactor. Don't attribute to "unrelated" without that check.

5. **Add gateway-mode integration tests (your follow-up #3 — not optional).** Unit/integration coverage for `docker_client.py` gateway mode (network create, route/resolv/sentinel injection, teardown) and the `egress_proxy.py` TPROXY decision path. This also closes the still-open S3.1 poller→breaker wiring-test gap (verdict-11), now that S3.1 polls the gateway.

**LLM provider auth (your follow-up #2):** an operator/config matter, not an engine defect — flag it to the operator; it's not yours to solve, but the enforced end-to-end scan in criterion 3 can't complete without it.

---

## Hold-the-line invariants (unchanged)

`decide()` / F1 / S3.1 reused with decision logic **byte-identical** (interception plumbing may change); SGL is removal-upstream only — never alter a disposition, add an `evidence_class`, or touch any file under `core/logic/`, `core/proposals/`, `core/oob/`, `core/diff/`, `core/race/`.

When you return, send the **full** live-proof evidence (all criteria, agent-as-root, including the `127.0.0.11` adversarial case) plus the PRE-1 confirmation. I validate the proof line-by-line before Part B closes and E1 is cleared.

---

```
Skill: pm-auditor@2.0.0 · validator: opus-4.8-pm-auditor
Reviewed: Part B impl + partial containment proof
Validated: agent-side hardening (no iptables / no NET_ADMIN), decide()-direct 403, route+resolv injection
Blocker: cross-netns REDIRECT fails → TPROXY required (diagnosis correct; honestly surfaced)
Decision: NEEDS-REVISION — TPROXY fix + full re-proof + PRE-1 confirmation + gateway tests
Gate: E1/paper remain blocked until the live-containment proof passes in full
```
