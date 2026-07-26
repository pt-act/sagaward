# Current Focus — strix

## Status (as of 2026-07-25T06:30Z)

**propose-dispose-validation spec: COMPLETE — round 2 APPROVED.**

Paper v1.0 is publication-ready. All four experiments live on the 13-pair corpus. All v1-release-checklist items done.

## Active Work
- None — strix propose-dispose validation cycle is closed.

## Next Up (if operator continues)
- DEV-7: fix path_traversal_proxy harness probe (Starlette URL decode edge case) — PD-VAL-7 backlog
- Mine additional real CVE pairs for corpus (currently 5/13 real; 8 synthesized)
- Phase 4: race_harness_tool — ✅ COMPLETE (merged to main, ca4fd09; pass-count not captured but CI green per PROGRESS.md)
- Phase 5: business_logic_orchestrator — ✅ COMPLETE (approved, merged to main e74f05e; 315 tests pass; see specs/phase-5-business-logic-testing/validation/completion-report.md)
  NOTE: "blocked on that phase" was stale — PROGRESS.md line 3 explicitly reconciled this 2026-06-18
- S0-v2 cross-container gateway mode proof on real Linux host
