# Coder Directive — SGL Deployment-Containment Fixes (post-Gate-5)

> From: PM/Validator (`opus-4.8-pm-auditor`) · To: Producer (CLI) · 2026-06-21
> Read alongside **verdict-09** (SGL-Core code approved) and **verdict-08** (round history).
> **Context:** SGL-Core's governance *logic* is approved and merged to `main` (PR #22). The
> first live engine run (the Gate-5 smoke) then FAILED, exposing deployment + containment
> defects that unit tests structurally could not catch. **None of these are governance-logic
> bugs** — they are in how the engine is *packaged and run*. This directive fixes them.
> Branch: cut **`sgl-deploy-fix`** off `main @ d8a6faa`.
> Producer routing: **Opus** — this is S0 containment (security-critical).

---

## Why you're getting this (the failure, in one paragraph)

We pointed the real engine at a target for the first time with `STRIX_EGRESS_ENFORCE=1` and an
**empty scope** (which must mean "deny all"). A `curl` to `example.com` **succeeded** — a
fail-OPEN egress bypass. Root cause has two layers, and both must be fixed:

1. The in-container decision proxy **crashed at startup** (couldn't import its own package), so
   there was no enforcement at all.
2. Even with the proxy healthy, the **agent runs as root**, and the egress firewall *exempts
   root* — so the agent's traffic skips the redirect entirely, and root could `iptables -F` the
   rules anyway. The containment is void for a root agent.

The governance code is fine. The container was never built/run with the full package, and the
agent was never actually verified to run unprivileged. That's what this fixes.

---

## FIX 1 — PRE-4: the prod-image decision proxy crashes (fail-open)

**Symptom (observed):**
```
ModuleNotFoundError: No module named 'strix.core.govern.limiter'
  at /opt/strix-python/strix/runtime/egress_proxy.py:49
     from strix.core.govern.scope import (...)
  -> strix/core/govern/__init__.py:5  from strix.core.govern.limiter import CredGuard, RateLimiter
```

**Why:** the S2–S8 merge made `strix/core/govern/__init__.py` eagerly import the agent-side
modules (`limiter`, `ownership`, …). The egress proxy does `from strix.core.govern.scope import
…`, which runs `govern/__init__.py` first — which now needs `limiter`/`ownership`. But
`containers/Dockerfile.prod` only `COPY`s `scope.py` + `egress_proxy.py` into the image. So in
the container the import explodes, the proxy process dies, and **nothing enforces egress.** The
prod image was never rebuilt+retested after S2–S8 landed.

**Fix (decided — do the simple, robust one):** those 5 agent-side modules only import `scope`
(verified: their sole `strix` import is `from strix.core.govern.scope import …`), so just bake
them into the image. Add next to the existing `COPY strix/core/govern/scope.py …` line in
`containers/Dockerfile.prod`:
```dockerfile
COPY strix/core/govern/limiter.py      /opt/strix-python/strix/core/govern/limiter.py
COPY strix/core/govern/ownership.py    /opt/strix-python/strix/core/govern/ownership.py
COPY strix/core/govern/breaker.py      /opt/strix-python/strix/core/govern/breaker.py
COPY strix/core/govern/cost_ceiling.py /opt/strix-python/strix/core/govern/cost_ceiling.py
COPY strix/core/govern/audit.py        /opt/strix-python/strix/core/govern/audit.py
```
(Optional cleaner follow-up, your call to note not do now: make `govern/__init__.py` not eagerly
import the agent-side modules so the in-container enforcer needs only `scope.py`. Either is fine;
the COPY is lowest-risk and unblocks immediately.)

**Necessary but NOT sufficient** — FIX 2 is the real containment fix.

---

## FIX 2 — PRE-3: the agent runs as root, defeating the egress firewall (the critical one)

**Symptom (observed):** `docker exec <sandbox> id -un` → **root**. Empty-scope `curl` → BYPASS.

**Why — read this carefully, it's the crux of S0:**
- `containers/egress-enforcer.sh` installs an iptables OUTPUT REDIRECT that sends agent traffic
  to the decision proxy, with one exemption: `-m owner --uid-owner 0 -j RETURN` (so the proxy's
  *own* forwarding isn't redirected back into itself). That exemption is **for uid 0 = root**.
- `strix/runtime/docker_client.py` sets `create_kwargs["user"]="root"` so the entrypoint can
  install the iptables rules. **Docker uses that create-user as the default for `docker exec`
  too** — not the Dockerfile `USER pentester`. (This is the assumption verdict-04 got wrong; the
  earlier "passing" SP3s forced `su pentester`, which masked it.)
- So the agent's tools exec as **root** → they match the `--uid-owner 0 RETURN` exemption →
  their traffic **skips the redirect and goes straight out**. And root can `iptables -F` the
  rules with no sudo. The firewall is decorative for this agent.

**Fix (decided — confirmed viable in the SDK):** make the agent's tools exec as **pentester**,
not root. The openai-agents SDK already supports this:
- `agents/sandbox/capabilities/tools/shell_tool.py:99` → `session.exec(command, …, user=user)`
- `user` comes from `_agent_run_as_user(agent)` → returns **`agent.run_as`**
  (`runtime_session_manager.py:723`). If `agent.run_as is None`, the SDK passes no user → exec
  defaults to the container user (root). **strix sets `run_as` nowhere**, hence root.

So: in `strix/agents/factory.py`, where the Strix agent(s) are built (`build_strix_agent` /
`make_child_factory`), set **`run_as="pentester"`** on the agent — gated on enforcement:
```python
# pseudo — set on the SandboxAgent construction for root + every child
run_as = "pentester" if os.environ.get("STRIX_EGRESS_ENFORCE") == "1" else None
agent = SandboxAgent(..., run_as=run_as)
```
Keep `create_kwargs["user"]="root"` in `docker_client.py` (the entrypoint still needs root to
install iptables). The result is the separation that actually works: **entrypoint = root
(installs the firewall once at boot); agent tools = pentester (subject to the redirect, and
sudo-revoked so they can't flush it).**

**Why this fully closes it:**
- pentester traffic is NOT uid-0-exempt → it hits the REDIRECT → goes through the decision proxy
  → enforced (empty scope ⇒ DENY ⇒ blocked).
- pentester can't `iptables -F` (sudo was revoked in the prod image at S0/S1).
- `nmap -sS` etc. still work for pentester because the base image grants file capabilities
  (`setcap cap_net_raw,cap_net_admin … nmap`) — non-root raw sockets are fine.

---

## Order of implementation

```
1. FIX 1  Dockerfile.prod — COPY the 5 govern modules   (proxy can load)
2. FIX 2  factory.py — agent.run_as="pentester" when STRIX_EGRESS_ENFORCE=1   (agent is non-root)
3. Rebuild:  docker build -f containers/Dockerfile.prod --target prod -t strix-sandbox:prod .
4. Re-run the Gate-5 smoke (below) — BOTH must hold:
     - empty scope  ⇒ curl/dns/nmap BLOCKED   (fail-closed)
     - in-scope host ⇒ reachable               (F1 ALLOW)
     - agent tools run as pentester             (id -un = pentester, via the SDK path)
5. uv run pytest tests/ -q + ruff check . → paste both tails (no subset)
6. File completion report; hand to PM.
```

## Verification you must pass (paste outputs)

**A — SDK-path exec user (the PRE-3 proof).** During a live run, or via the SDK session, confirm
a tool command reports `pentester`. The decisive deterministic check mirrors the SDK
(create root + tool-exec user): if you can't easily run the engine, at minimum show the
`run_as` wiring + a unit/integration assertion that the agent is constructed with
`run_as="pentester"` under enforcement.

**B — Egress both directions on the rebuilt image, with the agent as pentester:**
- empty scope: `curl https://example.com` ⇒ **BLOCKED** (not the page)
- in-scope: with `STRIX_SCOPE_RULES` set to the target host/IP ⇒ reachable
- `iptables -t nat -F` attempted as the agent user ⇒ denied (no sudo) and egress still blocked

**C — full suite green + ruff clean** (paste `pytest tests/ -q` tail and `ruff check .` tail).

---

## Definition of Done
- [ ] FIX 1: 5 `COPY` lines in `Dockerfile.prod`; prod image's egress proxy starts without import error.
- [ ] FIX 2: `agent.run_as="pentester"` under enforcement in `factory.py`; `create user=root` kept.
- [ ] Rebuilt `strix-sandbox:prod`: empty-scope egress BLOCKED, in-scope reachable, **`id -un`=pentester**, `iptables -F` denied.
- [ ] `pytest tests/ -q` green (the 4 PRE-1 bl-fixture Docker tests may remain — they're pre-existing; note them) + `ruff check .` no new errors.
- [ ] Completion report per VALIDATION_PROTOCOL §C with pasted evidence for A/B/C.

## Out of scope / tracked separately (do NOT do here)
- **PRE-1** — the 4 `test_business_logic_fixture` full-suite Docker failures: pre-existing
  Phase-5 defect (fails on `main` too). Separate track.
- **S3.1** — breaker measures agent-cycle not target-request health: deferred, gates unattended
  non-owned-target use, not E1–E4. See `pm-decision-breaker-target-health.md`.
- **PRE-2** — inventory `strict_mode=False`: already fixed + on `main` (`d8a6faa`).

## What changes in the record
This reopens **S0 containment**. verdict-04's approval of "create-root entrypoint / Dockerfile-
USER-pentester exec" was based on a wrong Docker exec-user assumption; the correct mechanism is
the SDK `run_as`. Once FIX 2 passes the B checks, S0 containment is genuinely re-validated and
the Gate-5 HOLD LINE can be re-attempted.
