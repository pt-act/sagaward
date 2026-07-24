# PR #18 merge-conflict resolution — `propose-dispose-validation` → `main`

**Conflicts (3):** `strix/report/state.py` (content), `tests/test_proposals_assembler.py` (add/add), `tests/test_proposals_disposer_wiring.py` (add/add).

**Resolution: take the branch side for all three.** Verified: merged tree gives 370 passed / 4 skipped / 19 subtests; ruff + format + mypy clean; zero conflict markers.

## Why the branch side, for each file

- **`state.py`** — The branch carries the validated **link-only** design: `_link_disposer_verdict_to_funnel` only attaches the `report_id`, and the *verdict* is recorded once from the single emit point `record_harness_run` (driven by the factory emit-wrapper). `main` (PR #16) still records the "confirmed" verdict inside the link path and lacks `record_harness_run` / `_match_recordable_proposal`. After resolution the four funnel methods appear exactly once each, in order: `_link_disposer_verdict_to_funnel` → `record_harness_run` → `_match_recordable_proposal` → `_match_open_proposal`.
- **`test_proposals_disposer_wiring.py`** — This is **not** optional. The branch's `state.py` is link-only, so the test must assert `record.verdicts == []` (report id linked, verdict owned by the emit-wrapper). `main`'s version asserts the old behavior (`len(record.verdicts) == 1`, "confirmed") and **fails** against the branch's link-only code. Take the branch version.
- **`test_proposals_assembler.py`** — The branch is a functional superset: adds `import inspect`, the wider models import (`ProposalContext`, `assembler as assembler_mod`), and the strengthened `test_boundary_is_structural` (the Spec A verdict's minor-2 fix). No test is lost.

`strix/core/proposals/` and `strix/report/proposals.py` are byte-identical on both sides (PR #16 and this branch are two cuts of the same feature), so the branch's tests hold on the merged tree.

## Option A — resolve locally and push (recommended)

```bash
git fetch origin
git checkout propose-dispose-validation
git merge origin/main
# take the branch side for all three conflicted files:
git checkout --ours strix/report/state.py tests/test_proposals_assembler.py tests/test_proposals_disposer_wiring.py
git add strix/report/state.py tests/test_proposals_assembler.py tests/test_proposals_disposer_wiring.py
git commit --no-edit          # completes the merge
uv run pytest tests/ -q       # expect: 370 passed, 4 skipped, 19 subtests
git push origin propose-dispose-validation
```

> `--ours` = the PR branch side here, because you are *on* `propose-dispose-validation` merging `main` *in*. (Inside GitHub's web "Resolve conflicts" editor there is no ours/theirs — just replace each conflicted file's full contents with the matching `*.resolved` file in this folder, then "Mark as resolved" → "Commit merge".)

## Option B — drop in the resolved files

The three `*.resolved` files in this directory are the exact merged contents. Copy each over its counterpart (strip the `.resolved` suffix), `git add`, and commit the merge.

## After merging
- Re-run the full gate on the merged result (above).
- Then proceed with the build per the pre-build validation verdict, and **lock `planning/E2-preregistration.md` before reading any E2 outcome.**
