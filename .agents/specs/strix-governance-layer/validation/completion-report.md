# Completion Report — strix-governance-layer (S0 + S1) — round 4

## Header

```
spec_id:       strix-governance-layer
producer:      claude-opus-4-8[1m]
started:       2026-06-18 18:00 UTC
completed:     2026-06-19 00:15 UTC
spec_version:  no explicit semver in spec header; Gate 1 PASS recorded in spec.md
prior_reports: round 1 (needs_revision, verdict-01.md),
               round 2 (needs_revision, verdict-02.md),
               round 3 (operator-directed correction — entrypoint/exec user separation)
revision_addresses: docker exec default-user bypass (USER root defeated sudo revocation)
```

---

## Artifacts Produced

Unchanged (S1, DNS fix, sudo revocation — all confirmed in prior verdicts):
- `strix/core/govern/__init__.py`, `strix/core/govern/scope.py`, `tests/test_govern_scope.py`
- `strix/runtime/egress_proxy.py`, `containers/egress-enforcer.sh`

Revised for round 4 (three changes only, no other modifications):
- `containers/Dockerfile.prod` — final directive `USER root` → `USER pentester`
- `strix/runtime/docker_client.py` — `create_kwargs["user"] = "root"` added inside the `if enforce == "1":` block
- `containers/docker-entrypoint.prod.sh` — comment-only update (no logic change)

---

## Acceptance Criteria Self-Check

**AC-G1 — Production image builds with all pinned tools and egress enforcer active; no tool can reach the network except through it.**

- Claim: partially met (authored; build not yet run)
- Evidence:
  - `containers/Dockerfile.prod:91` — final `USER pentester` (the `docker exec` default). Pentester has no sudo (revoked at `Dockerfile.prod` `sed -i '/pentester.*ALL/d' /etc/sudoers && visudo -c`).
  - `strix/runtime/docker_client.py:133` — `create_kwargs["user"] = "root"` inside the `if enforce == "1":` block, so the container's primary process (the prod entrypoint) runs as root and can install iptables rules.
  - `containers/docker-entrypoint.prod.sh` — runs the enforcer directly (no sudo), delegates to the dev entrypoint.
  - The bypass identified in the operator correction (USER root → `docker exec` defaults to root → sudo revocation defeated) is closed: the entrypoint user and the exec-default user are now distinct.
- Notes: AC-G1 remains unverifiable without operator image build + SP3.

---

**AC-G2 — Fail-closed scope: DENY/UNKNOWN/EXPIRED/no-rules blocks.**

- Claim: met (S1 unchanged; DNS enforcement confirmed in verdict-02.md)
- Evidence: No change to `scope.py` or `egress_proxy.py` this round. S1 paths and DNS enforcement were confirmed by the validator in verdict-01.md (§AC-G2) and verdict-02.md (§AC-G2 adversarial trace).

---

**AC-G3 through AC-G7** — not met (S2–S6, unchanged scope)

**AC-G8 — Gate-neutral** — met (static import boundary unchanged; the round-4 delta touches only `containers/` and `runtime/docker_client.py`, none of `core/logic`, `core/proposals`, `core/oob`, `core/diff`, `core/race`)

**AC-G9 — Audit** — partially met (proxy logging present; S6 structured log deferred)

**Non-functional — Fail-closed / No LLM in path / Additive** — all met (unchanged; no engine imports introduced)

---

## Interfaces Delivered

`decide` — unchanged, `strix/core/govern/scope.py:209`.

No new public interface this round. The round-4 change to `docker_client.py` is internal container-create wiring (`create_kwargs["user"]`), not a declared spec interface.

---

## Known Deviations

1. **`decide()` consolidates `action_class` into `Target`** — compatible, documented round 1.
2. **SP3 unverified pending operator image build** — unchanged.
3. **AC-G3/G4/G5/G6/G7 not implemented** — S2–S6, unchanged scope.
4. **AC-G9 partially met** — S6 structured log deferred.
5. **Root (uid 0) exempt from iptables REDIRECT** — compensating control is full sudo revocation for pentester AND pentester as the `docker exec` default user, so agent tools never run as root and never have sudo.

---

## Changes Made for Round 4 (operator-directed correction)

**Root cause:** Round 3 set `USER root` as the final Dockerfile directive. The OpenAI Agents SDK runs agent tools via `docker exec`, whose default user is the Dockerfile `USER`. With `USER root`, every tool execution ran as root — an agent already running as root needs no sudo to run `iptables -t nat -F`, so the sudo revocation was fully defeated.

**The Docker mechanism that fixes it:** Docker applies two different user settings:
- The **create-time `user=`** argument (`containers.create(user="root")`) governs the container's **primary process** — the ENTRYPOINT.
- The **Dockerfile `USER`** directive governs the **`docker exec` default**.

By setting these independently, the entrypoint (which installs iptables rules) runs as root, while agent tools run as pentester.

**Change 1 — `containers/Dockerfile.prod`:**
```dockerfile
USER pentester   # was: USER root
```
Final directive before `ENTRYPOINT`. This is the `docker exec` default. Pentester has no sudo.

**Change 2 — `strix/runtime/docker_client.py`** (inside `if enforce == "1":`, after env injection):
```python
create_kwargs["user"] = "root"
```
Sets the primary-process (entrypoint) user to root at container-create time, overriding the Dockerfile USER for the entrypoint only. `docker exec` is unaffected and still defaults to pentester.

**Change 3 — `containers/docker-entrypoint.prod.sh`:** comment-only update. The script still runs `/usr/local/sbin/strix-egress-enforcer` directly and delegates to the dev entrypoint; the header comment now states it runs as root because `docker_client.py` passes `user="root"` at create time, not because the Dockerfile sets `USER root`.

No other files were modified. (`scripts/*.sh` execute bits were re-dropped by a `.venv` rebuild during testing and restored via `git checkout origin/main -- scripts/*.sh` so they stay out of the commit.)

---

## State Management

### Progress Tracking

- Spec file: `.agents/specs/strix-governance-layer/spec.md`
  - All boxes checked: no (S0 boxes pending SP3 build; S2–S8 not started)

### Memory Bank

- File: `.agents/memory_bank/active/PROGRESS.md`
  - Action: appended
  - Content summary: round-4 entry — entrypoint/exec user separation; USER pentester final + create-time user=root; gate 406

- File: `.agents/memory_bank/active/current_focus.md`
  - Action: updated
  - Content summary: commit ref updated to 7ab966a; resumption point unchanged (operator SP3 build)

### Progress Entry

```markdown
### 2026-06-19 (round 4 — entrypoint/exec user separation)
- **Implemented:** SGL S0 operator-directed correction. Round-3's `USER root` final directive made `docker exec` default to root, defeating the sudo revocation (SDK runs tools via docker exec). Fix: Dockerfile.prod final `USER pentester` (exec default, no sudo); docker_client.py passes `create_kwargs["user"]="root"` inside the enforce block (entrypoint runs as root for iptables setup); docker-entrypoint.prod.sh comment-only update. Three files only. Gate: 406 passed.
- **Decided:** Docker separates entrypoint user (create-time `user=`) from exec default (Dockerfile USER); use both to keep the enforcer root-owned while agent tools run as pentester.
- **Blocked:** SP3 requires operator image build.
- **Next:** push 7ab966a; operator builds strix-sandbox:prod, runs SP3 — incl. confirming `docker exec` lands as pentester and `sudo` is absent; validator round 4.
```

---

## Handoff Notes

- **Gate:** 406 passed, 4 skipped, 19 subtests. No regressions.
- **Commit:** `7ab966a` on branch `sgl-s0-s1` (local; awaiting token to push).
- **Full branch log after this commit:**
  ```
  c4bfcb9  feat(sgl-s1): fail-closed scope decision service + SP1/SP2 PBT
  aba137f  fix(sgl-s1): correct SP2 test oracle to mirror first-match-wins semantics
  b34db7a  fix(sgl-s0): close DNS enforcement gap + restrict pentester sudo
  d448237  fix(sgl-s0): revoke pentester sudo entirely; run prod ENTRYPOINT as root
  7ab966a  fix(sgl-s0): separate entrypoint user (root) from exec default (pentester)
  ```
- **SP3 must now also verify the exec-default user.** Add to the adversarial test:
  ```bash
  # Confirm docker exec lands as pentester (not root) and sudo is absent
  docker run -d --name sgl-sp3 --cap-add NET_ADMIN --cap-add NET_RAW \
    -e STRIX_EGRESS_ENFORCE=1 -e STRIX_SCOPE_RULES="" strix-sandbox:prod
  docker exec sgl-sp3 id -un                       # expected: pentester
  docker exec sgl-sp3 sh -c 'command -v sudo || echo NO-SUDO'   # expected: NO-SUDO
  docker exec sgl-sp3 sh -c 'sudo iptables -t nat -F 2>&1 || echo BLOCKED'  # expected: BLOCKED
  docker exec sgl-sp3 sh -c 'curl -s --max-time 5 https://example.com && echo BYPASS || echo BLOCKED'  # expected: BLOCKED
  docker rm -f sgl-sp3
  ```
  Note: the entrypoint itself must still come up as root — verify the iptables rules are installed (`docker exec sgl-sp3 sh -c 'iptables -t nat -L STRIX_EGRESS'` succeeds, run as the implicit pentester it will need the rules already in place from the root entrypoint).
- **`_scope.py` untouched** — S7 integration deferred.
