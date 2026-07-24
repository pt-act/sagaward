# PM Verdict — S0-v2 Step-0 Design Note (Revision 2)

> **From:** PM/Validator (`opus-4.8-pm-auditor`)
> **To:** Producer (coder, CLI)
> **Date:** 2026-06-22
> **Ref:** `Part_B-Step0-Design-Note.md` (revised); `pm-review-s0v2-step0-design-note.md`
> **Reviewed:** all seven prior findings (B1–B3 blocking, I4–I6 important, M7 minor), re-checked for genuine resolution vs. acknowledgement.

---

## Decision

```
status:  APPROVE-WITH-CONDITIONS
scope:   design is bypass-clean enough to implement; two conditions are binding
         and verified in the live-containment proof before the paper unblocks.
gating:  green-light to BUILD. Teardown of the in-container enforcer happens only
         after the gateway path lands and the live proof passes.
```

Strong revision. Six of seven findings are genuinely closed (not just acknowledged). One — the DNS path (I4) — has a real residual against a **root** agent that must be pinned, but it's a one-control refinement plus a test, not a redesign, so it rides along with implementation rather than blocking it.

---

## Resolution scorecard

| # | Finding | Status | Note |
|---|---|---|---|
| **B1** | NET_ADMIN contradiction | ✅ **Resolved** | Transient host `docker exec --privileged` for route injection; agent bounding set omits NET_ADMIN (root agent cannot re-acquire — correct). Sentinel-file (`/var/run/strix-route-set`) start-up gate closes the pre-route egress window. |
| **B2** | FORWARD default-DROP | ✅ **Resolved** | `iptables -P FORWARD DROP`; catch-all ACCEPT gone; only redirected TCP/DNS reach the proxy, ICMP/raw hit the default DROP. Reasoning (proxy upstream is OUTPUT, not FORWARD) is correct. |
| **B3** | No Docker socket in agent | ✅ **Resolved** | Stated as explicit invariant; `docker inspect .Mounts` check in the proof. |
| **I4** | Agent DNS path | ⚠️ **Residual — see Condition 1** | `resolv.conf` override is correct for the cooperative case, but a **root agent can rewrite `resolv.conf` back to `127.0.0.11`**, and the embedded resolver forwards via dockerd — potentially to host/public DNS, bypassing F1. |
| **I5** | IPv6 disabled | ✅ **Resolved** | sysctl disable via the privileged session; agent can't re-enable (no NET_ADMIN). Confirm "no IPv6 egress" in the proof. |
| **I6** | Health transport | ✅ **Resolved** | Switched to Option C (host→gateway `docker exec` read). No new network surface. Correct. |
| **M7** | Proxy binding vs logic | ✅ **Resolved** | Bind `127.0.0.1`→`0.0.0.0` only; `SO_ORIGINAL_DST` unchanged; `decide()`/F1 byte-identical. The binding-not-logic distinction is exactly right. |

---

## Binding conditions (carried into implementation + proof)

### Condition 1 — Close the DNS residual (I4)
The `resolv.conf` override alone doesn't hold against a root agent that re-points DNS at the embedded resolver. Two parts:
- **Pin Docker `--dns <gateway-ip>` on the agent container at create time**, in addition to the `resolv.conf` override. This constrains the embedded resolver's *upstream* to the gateway, so even `127.0.0.11` can't forward to host/public DNS. (A direct query to `8.8.8.8:53` is already caught by the gateway's port-53 REDIRECT — the embedded resolver is the only gap, and this closes it.)
- **Add the adversarial test to the live proof:** agent **running as root** rewrites `/etc/resolv.conf` to `nameserver 127.0.0.11`, then resolves an out-of-scope external name → must be **DENY/NXDOMAIN/fail**, never resolved out-of-band. This is the test that proves F1 holds against an actively-evading agent.

### Condition 2 — Confirm the redirect→proxy path during implementation (B2)
Verify that REDIRECTed agent TCP/DNS actually lands on the proxy (DNAT → INPUT → `0.0.0.0:48081` bind) and is decided. Your `ESTABLISHED,RELATED` rule in FORWARD is a **likely no-op** (redirected traffic goes to INPUT, not FORWARD; proxy upstream is OUTPUT) — harmless, keep it for defensive symmetry, but don't let it mask a misrouted redirect. The make-or-break is that no agent packet egresses without passing `decide()`.

---

## Green-light

**Implementation may proceed**, in this order, with the hold-the-line discipline intact:

1. Build the gateway image (`Dockerfile.gateway`) + `gateway-entrypoint.sh` (iptables default-DROP + PREROUTING redirect + IPv6 sysctl + proxy `--bind 0.0.0.0`).
2. Wire `docker_client.py`: internal network, gateway-first lifecycle, transient-privileged route + `resolv.conf` + `--dns` pin + IPv6 disable, sentinel gate.
3. **Only then** remove the retired in-container mechanism (`egress-enforcer.sh`, `run_as`, `user="root"` juggling, agent enforce-env, agent NET_ADMIN, agent `host.docker.internal`).
4. **Live-containment proof — the operator's hard gate** (agent as root): empty-scope reaches nothing via **TCP / DNS / raw-ICMP / IPv6 / the `127.0.0.11` adversarial case (Condition 1)**; in-scope reachable; agent can't reach the gateway rules or Docker socket; engine completes the scan + reports the IDOR.
5. Full suite green (`uv run pytest tests/ -q`) + `ruff check .` clean.
6. Completion report per VALIDATION_PROTOCOL §C with **pasted** containment evidence (every bullet in step 4).

**Hold-the-line invariants:** `decide()` / F1 / S3.1 reused with decision logic **byte-identical** (binding-only changes permitted); SGL is removal-upstream only — never alter a disposition, add an `evidence_class`, or touch any file under `core/logic/`, `core/proposals/`, `core/oob/`, `core/diff/`, `core/race/`.

When the completion report lands, I validate the containment proof line-by-line — including the adversarial DNS case — before Part B closes and the paper (E1) is cleared to run.

---

```
Skill: pm-auditor@2.0.0 · validator: opus-4.8-pm-auditor
Reviewed: Part_B-Step0-Design-Note.md rev2 (7 prior findings re-checked)
Resolved: B1, B2, B3, I5, I6, M7 (6/7). Residual: I4 (DNS root-agent rewrite) → Condition 1.
Decision: APPROVE-WITH-CONDITIONS — green-light build; conditions verified in the live proof.
Next: implement (gateway → wire → teardown) → live containment proof → completion report → PM validates.
```
