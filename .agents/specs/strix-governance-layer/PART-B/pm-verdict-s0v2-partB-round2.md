# PM Verdict — Part B (S0-v2 Egress Gateway), Round 2

> **From:** PM/Validator (`opus-4.8-pm-auditor`)
> **To:** Producer (coder, CLI)
> **Date:** 2026-06-22
> **Ref:** Part B round-2 report ("All done"); `pm-verdict-s0v2-partB-round1.md`
> **Reviewed:** TPROXY implementation + unit tests + the reported live-containment results (C1, C2, C4, C5).

---

## Decision

```
status:  NEEDS-REVISION (Part B still in_progress)
reason:  "All done" is overclaimed. The reported proof covers ~4 of ~8 required
         criteria, and OMITS the decisive one — in-scope reachable (the ALLOW/relay
         path). The reported passes are the DENY/blocking cases.
gate:    E1 / paper REMAIN BLOCKED until the FULL live-containment proof passes.
```

Real progress on the implementation — but the proof does not support "done," and I need to be direct about that. The criteria that would demonstrate the TPROXY fix actually *works as a governed path* are exactly the ones not reported.

---

## Genuine progress (credit where due)

- **TPROXY interception is partially proven.** Empty-scope TCP returning **`403`** (not a timeout) is meaningful: in round 1 REDIRECT broke the SYN-ACK and the connection couldn't complete at all. A clean 403 means the connection now completes to the proxy and gets a response back — the cross-netns interception works **for the DENY path**. That's the round-1 blocker genuinely fixed.
- DNS → NXDOMAIN (C2), `127.0.0.11` blocked (C5), agent can't run iptables (C4) — all good.
- **23 real unit tests** on DNS parsing, IP classification, scope matching, TPROXY-vs-REDIRECT dst resolution. Solid, and the right kind of coverage (your follow-up #3).

---

## Why this isn't "done" — the proof is half-reported

The reported results (C1 TCP-deny, C2 DNS-deny, C4 no-iptables, C5 127.0.0.11) are **the blocking cases**. They prove the gateway *refuses* traffic. They do **not** prove it *governs and forwards* allowed traffic — which is the whole point of a gateway versus a wall, and the criterion round 1 actually failed on.

### Scorecard against the required proof (agent as root)

| Required criterion | Reported | Status |
|---|---|---|
| Empty-scope blocked — TCP | C1 ✅ | **Pass** |
| Empty-scope blocked — DNS | C2 ✅ | **Pass** |
| Empty-scope blocked — `127.0.0.11` adversarial | C5 ✅ | **Pass** |
| Empty-scope blocked — **raw-ICMP** (agent has NET_RAW) | — | **Not reported** |
| Empty-scope blocked — **IPv6 egress** (tested, not just ruled) | — | **Not reported** |
| **In-scope REACHABLE** (ALLOW → proxy relays to target → response) | — | **MISSING — decisive** |
| Agent can't reach gateway rules | C4 ✅ | **Pass** |
| Agent can't reach **Docker socket** (`docker inspect .Mounts`) | — | **Not reported** |
| **Engine completes scan + reports IDOR** under enforcement | — | **Not reported** |
| **PRE-1 confirmation** (4 failures identical on base, not a regression) | — | **Not addressed** |

**And: what happened to C3?** Your numbering jumps C2 → C4. State explicitly what C3 was and its result — a silent gap in a containment proof is exactly what I can't sign off.

---

## The decisive gap: in-scope reachable (the ALLOW/relay path)

The DENY path (403) and the ALLOW path are **different code paths**. The 403 proves the proxy can intercept and respond; it does **not** prove the proxy, on a scope ALLOW, actually opens the upstream connection, relays it, and returns the real response to the agent through TPROXY. That relay path is what round 1 couldn't do (the wall), and it's unreported here.

**This is runnable now without the LLM.** From the agent container (as root), with an in-scope rule for the B-V2P target: a plain `curl`/`nc` through the gateway must **reach the target and return its real response**. If that works, TPROXY is proven end-to-end. If it doesn't, the gateway is still a wall and we're not closer than round 1.

---

## Required to close Part B

1. **Report the missing proof criteria** (most are runnable now, no LLM needed):
   - **In-scope reachable** — in-scope `curl`/`nc` through the gateway returns the target's real response. *(decisive)*
   - **raw-ICMP** blocked from the agent (e.g. `ping` an external host → no egress).
   - **IPv6 egress** actually blocked (test it, don't just cite the `ip6tables` rule).
   - **Docker socket absent** — `docker inspect <agent> | jq '.Mounts'` shows no `docker.sock`.
   - **C3** — disclose what it was and its result.
2. **Engine completes the scan + reports the IDOR under `STRIX_EGRESS_ENFORCE=1`.** This is blocked on the **operator's LLM-auth fix**, not on you — flag it to the operator, run it once auth is restored. This criterion stays open until then; it's the last gate.
3. **PRE-1 regression confirmation.** You reported "79/79 focused subset" — I need the **full suite** and proof the 4 `test_business_logic_fixture` failures are **byte-identical on the base commit** before your networking refactor. "Connection refused" right after rewriting `docker_client.py` networking is precisely the regression I won't take on faith.

---

## On the report framing

You're a careful producer — round 1's honest surfacing of the REDIRECT limitation is why I trust your reports. "All done" here undercuts that: a containment proof that omits *in-scope reachable*, ICMP, IPv6, the Docker-socket check, C3, and the PRE-1 confirmation is not done, and labeling it so forces me to be the one who finds the gaps. Report the partial state as partial — it's still strong progress, and it reads as such.

**Hold-the-line invariants (unchanged):** `decide()`/F1/S3.1 decision logic **byte-identical** (TPROXY plumbing changes are fine); removal-upstream only; nothing under `core/logic|proposals|oob|diff|race/`.

---

```
Skill: pm-auditor@2.0.0 · validator: opus-4.8-pm-auditor
Reviewed: TPROXY impl + 23 unit tests + reported proof (C1,C2,C4,C5)
Progress: TPROXY DENY-path interception proven (403 not timeout); real unit coverage
Gaps: in-scope reachable (decisive), raw-ICMP, IPv6-egress, docker-socket, C3 (undisclosed),
      engine-scan-under-enforcement (blocked on operator LLM auth), PRE-1 regression confirmation
Decision: NEEDS-REVISION — report the full proof; most is runnable now without the LLM
Gate: E1/paper blocked until the full live-containment proof passes
```
