# Open Questions

> AI → Human. Answered questions are removed and their resolutions recorded in PROGRESS.md / ARCHITECTURAL_DECISIONS.md. Reconciled 2026-07-24.

## 2026-06-21 · S3.1 poller→breaker wiring test — follow-up priority?
- **Context:** Verdict-11 flagged (non-blocking) that there's no direct test of the new feed path (poller → breaker; repeat_request 5xx/429 → breaker). The breaker unit tests pass but the S3.1 wiring is untested.
- **Question:** Priority follow-up before next real-target run, or defer?
- **Impact:** Closes the last S3.1 validation gap before gateway reuses target-health data.

## 2026-06-14 · TUI mypy debt (deferred)
- **Context:** ~69 pre-existing `mypy --strict` errors in `strix/interface/tui/`. Predate Phase 0, unrelated to feature work.
- **Decision:** Burn down in a dedicated pass when TUI is next modified.
- **Impact:** Gate definition is changed-files only; whole-repo clean is a later milestone.

## ✅ RESOLVED — 2026-06-21 · Funnel completeness for direct-filing disposers
- **Resolution (2026-07-24):** Option (ii) structural auto-registration implemented. `record_harness_run` in `strix/report/state.py` auto-registers a synthetic `ProposalRecord` when a confirmed harness run arrives with no prior proposal. Unconfirmed no-matches remain no-ops. Gate-neutral (`C ⊆ P`). 2 new tests added, full suite 568 passed.
- **Recorded in:** PROGRESS.md 2026-07-24 entry, ARCH #20.

## ✅ RESOLVED — 2026-06-21 · S0-v2 containment live-proof
- **Resolution (2026-07-24):** E1–E4 ran on owned B-V2P corpus (dev image, enforcement off). S0-v2 single-container REDIRECT design was live-proven in Round 3 (2026-06-22). Cross-container gateway mode implemented; real Linux host proof deferred as non-blocking.
- **Recorded in:** PROGRESS.md 2026-06-22 entry.

## ✅ RESOLVED — 2026-06-17 · Spec B harness-wiring approach
- **Resolution:** Option 3 centralized factory wrapper (`funnel_emit.py`), merged via PR #18.
