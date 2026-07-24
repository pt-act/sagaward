# PR #17 merge conflict — diagnosis & resolution

**PR #17** "Propose dispose validation" — head `propose-dispose-validation @ c0f76ed` → base `main @ e4897ce`. GitHub reports `mergeable: false` / `dirty`. Conflicts in `strix/report/state.py` and `tests/test_proposals_assembler.py`.

## Root cause — duplicate implementation, not divergent logic

The merge-base is `e74f05e` ("Dep cryptography (#13)"). Since then:

- **`main`** gained `e4897ce` **"Propose dispose (#16)"** — which independently added the propose-dispose instrumentation (the funnel: +94 lines in `state.py`, and the new `tests/test_proposals_assembler.py`, +190).
- **the branch** carries its own Spec-A lineage (`f51939f → 7f01b35 → f4b9637`) plus the Step-0 emit hook (`c0f76ed`).

So **PR #16 and PR #17 are two cuts of the same feature.** Crucially they are *not* divergent:

- `git diff main propose-dispose-validation -- strix/core/proposals/ strix/report/proposals.py` is **empty** — the instrumentation module is **byte-identical** on both sides.
- In `state.py`, the shared Spec-A methods (`_link_disposer_verdict_to_funnel`, `_match_open_proposal`, `FunnelLog` wiring, the `proposal_id` plumbing) **auto-merged cleanly** (identical on both sides). Only the branch's **extra** Step-0 methods conflicted.

## The two conflicts

### 1. `strix/report/state.py` — 1 hunk (content)
The branch inserts `record_harness_run` + `_match_recordable_proposal` between `_link_disposer_verdict_to_funnel` and `_match_open_proposal`; `main` has nothing there. The `HEAD` side of the hunk is empty.

**Resolution: keep the branch's inserted block** (purely additive — `main` lacks these methods). The merged file then has all four methods, once each, in order: `_link_disposer_verdict_to_funnel` → `record_harness_run` → `_match_recordable_proposal` → `_match_open_proposal`. Every symbol the new block references (`_VALID_EVIDENCE_CLASSES`, `ProposalRecord`, `funnel_log.record_harness_verdict`) is already present in `main`'s `state.py`.

### 2. `tests/test_proposals_assembler.py` — add/add (3 hunks)
Both PRs created this file. The branch's version is a **functional superset** of main's: identical content **plus** `import inspect`, `from strix.core.proposals import assembler as assembler_mod`, `ProposalContext` added to the models import, and the strengthened **`test_boundary_is_structural`** test (the Spec-A verdict's minor-2 fix). The only line "removed" relative to main is the narrower models import, *superseded* by the wider one — no test is lost.

**Resolution: take the branch side in full** (`git checkout --theirs`). Because `strix/core/proposals/` is identical on both sides, the strengthened test passes against the merged tree.

## Verification (performed)

- Reproduced the merge in a throwaway worktree; resolved both files by taking the branch side.
- **Zero conflict markers** remain; both files `py_compile` clean and `ast.parse` clean (Python 3.11 check).
- `state.py`: the four funnel methods appear exactly once, correctly ordered; all referenced symbols defined.
- `strix/core/proposals/` + `strix/report/proposals.py` are identical main↔branch, so the branch's assembler tests (green at `c0f76ed`) hold on the merged tree.

> Note: the full `uv`-driven pytest run on the merged worktree was blocked by a sandbox interpreter-permission issue that appeared mid-session; the resolution correctness rests on the identical-module proof + compile/marker checks above, not on a re-run. Re-run `pytest tests/test_proposals_assembler.py tests/test_proposals_funnel.py` after applying, to confirm in your environment.

## Operator steps

```bash
git checkout propose-dispose-validation
git merge main
# take the branch side for both conflicted files:
git checkout --theirs strix/report/state.py tests/test_proposals_assembler.py
git add strix/report/state.py tests/test_proposals_assembler.py
git commit            # completes the merge
uv run pytest tests/ -q   # expect green
```

Resolved files for reference: `state.py.resolved`, `test_proposals_assembler.py.resolved` (in this directory).

## Important sequencing note

This resolution is for the branch **at `c0f76ed`** (the current PR head). The Spec-B work produced this session (harness wiring, M4, M2 — in `artifacts/patches/`) is **not yet committed** onto the branch. Apply those patches **after** this merge, then re-run the full gate. The wiring patch further changes `_link_disposer_verdict_to_funnel` (→ link-only) and `_match_recordable_proposal` (relaxed); since `main`'s versions of those are identical to the branch's pre-wiring versions, the patch applies without new conflicts.
