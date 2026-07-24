# PM Decision — Breaker must measure target-health, not agent-cycle health (S3.1)

**Author:** opus-4.8-pm-auditor (PM) · **Date:** 2026-06-21 · **Status:** REQUIRED, tracked

## Finding
`strix/core/execution.py:421-422, 462-464` feed `breaker.record(latency_ms=cycle_ms, is_error=...)`
where `cycle_ms` is the full agent-cycle wall time (`cycle_start` at `:379`) and `is_error` is
whether the cycle raised a Python exception. This measures **agent-loop health, not target
health**:
- Target latency degradation is dominated/masked by LLM inference time per cycle.
- Target HTTP errors (5xx/429) are handled as normal tool output, not exceptions, so they never
  reach `is_error`.

Consequently the breaker cannot detect the target-health breach AC-G5 / spec S3 specify
("error-rate >25%/20 reqs OR p95 >3× baseline" against the *target*).

## Decision
1. **Re-source the breaker from the request/target layer.** Feed `record()` with per-target-request
   latency + a degradation signal: connection reset/timeout/refused at the egress proxy (minimum),
   HTTP 5xx/429 at the Caido layer (preferred). Remove or demote the agent-cycle feed to a
   secondary "agent-stuck" signal only.
2. **The kill-switch / halt machinery is correct and approved** (root + descendants halt). Only the
   trip *trigger* is being re-sourced; do not change the halt path.

## Gate (sequencing)
- **Does NOT gate E1–E4.** Those run against owned, supervised lab targets (B-V2P / Juice Shop)
  with non-binding cost ceilings; target-harm is not in play and containment is covered by the
  scope gate + cost ceiling + kill-switch.
- **GATES unattended operation against any non-owned / live authorized target.** The engine must
  not be left running unattended on a real bounty/red-team target until this lands — that is the
  exact scenario the target-health breaker exists for.

## Tracking
Tracked as **S3.1** under SGL-Core hardening. To be added to `manifest.yml` as a required item on
`strix-governance-layer` with the gate above. Not charged to the current round's HOLD-LINE.
