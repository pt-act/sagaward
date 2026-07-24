# Coder Directive — PR #27: clean the branch, fix the manifest, HOLD the merge

> **From:** PM/Validator (`opus-4.8-pm-auditor`)
> **To:** Producer (coder, CLI) — branch owner `rial1`
> **Date:** 2026-06-22
> **Ref:** PR #27 (`sgl-s0v2-egress-gateway` → `main`); `pm-verdict-s0v2-partB-round3.md` (coming next); `strix-s0v2-cloud-vm-runbook.md`

---

## What this is

PR #27 currently shows commits that look "already merged" and is throwing a duplicate-content conflict. This directive cleans that up and gets the branch to a clean single S0-v2 delta — **without merging to main yet.** Part B is not validated; the merge waits for the containment proof to pass on a real-kernel Linux VM.

---

## Why the phantom commits appear (not a mistake — a known pattern)

`sgl-s0v2-egress-gateway` was stacked on `sgl-s3.1`. Prior work was **squash-merged** to main, which creates new SHAs — so the original S3.1 / bring-up commits aren't in main's ancestry, only their *content* is. Diffing the branch against main replays them, and identical content collides (e.g. the `typing` import). Same class as the PR #17 issue. The fix is a rebase onto current main, which drops the now-empty (already-merged) commits.

---

## Part 1 — Rebase the branch onto current main

```bash
git checkout sgl-s0v2-egress-gateway
git fetch origin
git rebase origin/main
```
Resolve conflicts as they surface:
- **`egress_proxy.py` typing import** → keep `from typing import Any, Final` (the file uses `Any` in `_write_target_health_event(**fields: Any)` and `Final` throughout). Drop the `main`-side `Final`-only line.
- **Any "already on main" duplicate-content conflict** → take main's version (it's the merged one). These commits should replay as empty and drop out.

Then:
```bash
git push --force-with-lease
```
- Use `--force-with-lease` (never plain `--force`).
- You own this branch, but confirm nobody else has it checked out before the force-push.

**Expected result:** PR #27 now shows only the genuine delta — ideally just the S0-v2 gateway commit (plus the legit `Remove .agents/ from tracking` cleanup, which stays — `.agents/` belongs in `.gitignore` per AGENTS.md).

---

## Part 2 — Correct the manifest status (do this in the cleanup)

The manifest currently has `strix-governance-layer: status: completed` with `produces` claiming "live-proven" and a self-asserted "verdict: all 7 PASS." That's inaccurate — no validator verdict was issued and the cross-container gateway is unproven. Per round-3:
- Flip status `completed` → `in_progress` (or `blocked`, `blocked_by: "cross-container containment unproven; requires real-kernel Linux host"`).
- Drop "live-proven" from the `egress_enforcement_substrate` shape.
- History is append-only (don't edit past entries) — add a new entry recording the PM round-3 verdict (needs-revision).

---

## Part 3 — DO NOT squash-merge to main yet

Hold the merge. Reasons (full detail in the round-3 verdict you'll get next):
- Part B isn't validated — the proof only covered the retired single-container design, tested non-root.
- The cross-container gateway is unproven; the proof on a real kernel is exactly what will confirm or change the gateway code. Don't merge security-critical containment whose core function is unverified.
- When it merges, it should be the **proven** version, with the manifest flip carried by a real validator verdict — not a self-asserted one.

The cleaned branch is the staging point for the proof, not a merge candidate yet.

---

## Part 4 — The forward sequence (so you know what's next)

1. **[this directive]** Rebase → resolve → push; fix the manifest status. Branch is now a clean S0-v2 delta.
2. **Read `pm-verdict-s0v2-partB-round3.md`** — defines what the containment proof must actually show (cross-container, agent-as-root, the real C4 test, in-scope reachable, the `127.0.0.1` adversarial case, PRE-1 confirmation).
3. **Operator provisions a real-kernel Linux VM** per `strix-s0v2-cloud-vm-runbook.md`. Gate: `systemd-detect-virt = kvm` **and** the `TPROXY_OK` probe pass before building.
4. **You run the proof from this branch on the VM** (clone + `git checkout sgl-s0v2-egress-gateway`).
5. **PM validates** the proof line-by-line.
6. **Then** squash-merge the clean, proven delta to main + flip the manifest to `completed` with the real verdict.

---

## Hold-the-line invariants (unchanged)

`decide()` / F1 / S3.1 decision logic **byte-identical** (TPROXY/binding plumbing may change); SGL is removal-upstream only — never alter a disposition, add an `evidence_class`, or touch any file under `core/logic/`, `core/proposals/`, `core/oob/`, `core/diff/`, `core/race/`.

---

```
Skill: pm-auditor@2.0.0 · validator: opus-4.8-pm-auditor
Action: rebase sgl-s0v2-egress-gateway onto origin/main → clean delta; fix manifest status; HOLD merge
Conflict rule: keep `from typing import Any, Final`; take main's side on already-merged duplicates
Next: round-3 verdict → VM provision (kvm + TPROXY_OK) → proof from branch → PM validate → then merge
```
