# E2 — WITHDRAWN (S-2)

**Status:** WITHDRAWN — 2026-11-21
**Finding:** S-2 (external code review, @Jason)
**Rebuild:** `artifacts/run_live_experiments.py`

## Why

The E2 result (`e2_gap_dictation.json` / `e2_gap_dictation.csv`) is not a valid
measurement of the FP-arm. Two defects made the comparison unable to fail:

1. **The Sagaward arm compared the patched container with itself.**
   `run_pair` called `_run_harness(pair, port_patch, port_patch)`. The harness is a
   differential: it fires only when the vuln side gains access and the patched side
   does not. With both ports on the patched container there is no differential, so
   `flip_confirmed` was always `False` and `sagaward_pd_correct_patch` was always
   `True` by construction.

2. **The baseline received the identical prompt for both sides.**
   The M4 patched-side prompt was built from the same `surface_map` as the vuln-side
   prompt. The model saw the same input twice, so its FP-arm measured its own
   determinism, not its ability to distinguish a patched deployment.

## What the rebuild changes

- The FP-arm now probes the patched container directly (`_probe_endpoint`) and asks
  whether the patch still grants the access the vulnerability requires. An incomplete
  patch fails the arm.
- The baseline's patched-side prompt is built from the patched container's own
  observed behaviour (`_build_surface_map(pair, observed_patch)`), so the two sides
  differ and the baseline can fail.

## What is retained

The original data is retained in `e2_gap_dictation.json` (with a `withdrawn` block)
and `e2_gap_dictation.csv` for audit. It is not a result and must not be cited until
the rebuilt experiment is re-run.
