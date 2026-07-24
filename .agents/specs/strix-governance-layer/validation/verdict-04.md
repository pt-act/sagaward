# Verdict — strix-governance-layer (S0 + S1) — round 4

## Header

```
spec_id:                     strix-governance-layer
validator:                   opus-4.8-pm-auditor
validator_distinct_from_producer: true  (producer: claude-opus-4-8[1m])
reviewed_completion_report:  completion-reportv4.md (round 4)
prior_verdicts:              verdict-01.md (needs_revision), verdict-02.md (needs_revision), operator-directed round 3
verdict_timestamp:           2026-06-19 00:30 UTC
branch_verified:             sgl-s0-s1 @ 7ab966a
```

---

## Decision

```
status: approved (authored substrate)
```

All three round-4 changes verified exactly. The Docker exec-default/entrypoint-user
separation is correctly implemented. The authored S0+S1 substrate is now sound. The
remaining `unverifiable` items (AC-G1 build, SP8 runtime) are correctly deferred to the
operator build + SP3 adversarial test phase, which is the next step.

---

## Per-Criterion Assessment

### AC-G1 — Production image builds with all pinned tools and egress enforcer active.

- Producer's claim: partially met (authored; build not yet run)
- Validator's finding: **unverifiable** — correctly scoped. The authored substrate is now
  sound; the build and SP3 adversarial test remain on the operator.
- Evidence reviewed:
  - `containers/Dockerfile.prod:96` — `USER pentester` is the final USER directive before
    ENTRYPOINT. This is the `docker exec` default. Pentester has no sudo (`sed -i
    '/pentester.*ALL/d'` confirmed in prior rounds). ✓
  - `strix/runtime/docker_client.py:139` — `create_kwargs["user"] = "root"` is inside the
    `if enforce == "1":` block (confirmed by reading lines 124–144 directly). This sets the
    primary-process user (entrypoint) to root at container-create time, independently of the
    Dockerfile USER. ✓
  - `containers/docker-entrypoint.prod.sh` — comment updated correctly; logic unchanged;
    runs enforcer directly as root, delegates to dev entrypoint. ✓
  - Commit `7ab966a` contains **three files only**: `containers/Dockerfile.prod`,
    `containers/docker-entrypoint.prod.sh`, `strix/runtime/docker_client.py`. Scripts mode
    changes are working-tree only; not in the commit. ✓

- **Adversarial trace of the bypass surface (validator-constructed):**
  - Agent tool path: SDK → `docker exec <container> <tool>` (no -u flag) → Docker applies
    Dockerfile USER → pentester. Pentester has no sudo → `iptables -t nat -F` fails
    (EPERM, non-root) → bypass impossible without sudo. ✓
  - Indirect sudo path: `sudo bash -c 'iptables …'` → sudo absent (revoked) → BLOCKED. ✓
  - Entrypoint path: `containers.create(user="root")` → entrypoint runs as root → iptables
    rules installed → enforcement active before any agent tool exec. ✓
  - The separation is structural: Docker applies `create_kwargs["user"]` to the primary
    process and the Dockerfile USER to exec independently. This is not a convention — it is
    a Docker API property. ✓

---

### AC-G2 — Fail-closed scope: DENY/UNKNOWN/EXPIRED/no-rules blocks.

- Producer's claim: met (unchanged)
- Validator's finding: **confirmed** (carried from verdict-01/02 adversarial traces; no
  change to `scope.py` or `egress_proxy.py` this round)

---

### AC-G3 through AC-G7 — not met (S2–S6, correctly scoped)

---

### AC-G8 — Gate-neutral.

- Producer's claim: met (unchanged)
- Validator's finding: **confirmed** — round-4 delta touches only `containers/` and
  `runtime/docker_client.py`. Zero changes to `core/logic`, `core/proposals`, `core/oob`,
  `core/diff`, `core/race`, `report/`, `agents/factory.py`. Import boundary unchanged.

---

### AC-G9 — Audit: every allow/deny/halt decision logged.

- Validator's finding: **confirmed partial** — unchanged; correctly deferred to S6.

---

### Non-functional — Fail-closed / No LLM in path / Additive.

- Validator's finding: **confirmed** — no new imports; no engine edits; Docker separation
  is additive to existing create_kwargs handling.

---

## Interface Verification

- `decide` — unchanged, `strix/core/govern/scope.py:209`. **compatible** (action_class in
  Target — documented deviation, carried from round 1).

---

## Issues Found

None. The three required changes are exact and correct. No undeclared changes in the commit.

---

## SP3 Adversarial Test — validated test protocol

The round-4 handoff adds `docker exec sgl-sp3 id -un` → expected: `pentester`. This is the
correct test for the exec-default user and must be the **first check** in the SP3 run —
it verifies the foundational premise before testing egress blocking. The full SP3 sequence
from the handoff notes is correct and complete.

---

## Verdict Rationale

The round-4 changes are exact: `USER pentester` as the final Dockerfile directive, `create_kwargs["user"] = "root"` inside the governance enforce block, comment-only entrypoint update. The Docker API separation between the create-time user (entrypoint) and the Dockerfile USER (exec default) is correctly understood and correctly applied. The bypass surface identified in round 3 (agent tools running as root via exec, defeating sudo revocation) is now structurally closed. The authored S0+S1 substrate is approved. The outstanding unverifiable items (AC-G1 build, SP8 runtime gate-neutrality on a live B-V2P pair) are correctly deferred to the operator build phase and are not blockers for this approval.

---

## Session Manifest

```
Skill: pm-auditor@2.0.0 + validation-upgrade-adversarial-semantics (v2.1)
Interpreter: opus-4.8-pm-auditor
Role: validator
Spec: strix-governance-layer (S0+S1)
Validation round: 4
Branch: sgl-s0-s1 @ 7ab966a
Files read: git show --stat 7ab966a, Dockerfile.prod tail, docker_client.py lines 120-145,
            docker-entrypoint.prod.sh (full)
Criteria verified: 7 confirmed, 0 refuted, 2 unverifiable (AC-G1 build; SP8 B-V2P runtime)
Decision: approved
Prior conflict: yes — rounds 1-3 were needs_revision; round 4 approved.
Post-conflict convergence: arbiter not required — the resolution was operator-directed
  correction (not producer-validator negotiation), so the convergence-audit trigger does
  not apply per VALIDATION_PROTOCOL §D.
Self-check result: passed (11 items including v2.1 adversarial direction check)
Drift observed: no
Escalations: none
```
