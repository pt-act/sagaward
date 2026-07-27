# Phase 4 — Race-Condition Harness: Validation Verdict

**Grade:** ◑ (partial — validated indirectly)

## Summary

Phase 4 (`_run_race_harness`) is validated indirectly via Phase 5 Contract-F integration.
The race harness tool is present in `_BASE_TOOLS` (position 42 of 46), registered without
curation in the MCP wrapper, and exercisable through `strix_run_engagement`.

## Evidence

- **Merge commit:** `ca4fd09`
- **Tool presence:** `_run_race_harness` in `_BASE_TOOLS` tuple (factory.py line ~415)
- **MCP passthrough:** `strix_corpus_status` → `native_capabilities` includes `_run_race_harness`
- **I6 compliance:** No capability curation — all 46 tools available in engagement
- **Contract-F binding:** Phase 5 business-logic violation tests depend on race-condition
  primitives; successful Phase 5 execution implies Phase 4 infrastructure is functional

## Why ◑ (not ●)

Full validation (●) requires a live Docker fixture with a race-vulnerable B-V2P pair
and end-to-end funnel confirmation. The corpus includes the `_run_race_harness` disposer
evidence type but no dedicated race-condition B-V2P pair has been deployed for isolated
Phase 4 testing yet. The indirect validation via Contract-F is sufficient for the
Phase 5 MCP wrapper milestone.

## Next Steps

- Deploy a race-condition B-V2P fixture pair
- Run isolated `_run_race_harness` through MCP → confirm funnel record
- Upgrade grade to ● upon direct confirmation
