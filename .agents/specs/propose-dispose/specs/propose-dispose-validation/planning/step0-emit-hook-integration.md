# Step-0 Funnel Emit-Hook — Integration Design (decision needed)

**Status:** mechanism landed (`ReportState.record_harness_run`, `c0f76ed`); harness-tool wiring pending.
**Goal (verdict path a):** the funnel records **every** harness run (confirmed + unconfirmed) so
`Prec_gate = |C∩V|/|C|` and `funnel_efficiency = harness_runs/|C|` are unbiased. Spec A records confirmed
runs only.

## Constraint
The hook must be **behavior-identical / gate-neutral**: it must not change what any harness confirms or any
`evidence_class` it assigns. It is observability only (`C ⊆ P` preserved). The validator will trace this.

## The fork
Wiring interacts with Spec A's approved confirmed-report path (`_link_disposer_verdict_to_funnel`, which
records a `confirmed` verdict + `report_id` at report time, matching via `_match_open_proposal`, which
requires a verdict-free proposal). Three options:

| Option | What | Pros | Cons |
|---|---|---|---|
| **1. Emit at non-report exits only** | Call `record_harness_run` at each harness's unconfirmed / deduped-confirmed return; leave the confirmed→report path to Spec A. | No double count; Spec A path untouched. | An emitted unconfirmed verdict makes the proposal non-"open", so a later confirmed report for the same proposal won't link via `_match_open_proposal` (rare same-proposal flip). Per-harness edits at scattered return points. |
| **2. Emit at all harness exits; report path → link-only** | The emit-hook is the single per-run recorder; `_link_disposer_verdict_to_funnel` stops adding a verdict and only attaches `report_id`. | One clean recording point; correct counts. | Modifies approved Spec A confirmed-path behavior + its tests; kickoff says `report/state.py` "unmodified beyond the additive emit-hook". |
| **3. Centralized factory wrapper** | One pass-through wrapper around the harness tools in `factory._BASE_TOOLS` emits from each tool's return value; returns it unchanged. | Behavior-identical by construction; no edits inside disposer logic; single seam. | Needs a small per-harness result adapter (verdict/evidence_class/endpoint shapes differ across oob/race/diff/logic). |

## Recommendation
**Option 3** (centralized wrapper) best honors "behavior-identical" and "disposer unchanged" — the disposer
function is literally unmodified; we only observe its output at the registration boundary. Reconcile the
double-count with Spec A by having the wrapper be the sole per-run recorder and the report path attach only
`report_id` (a tiny, test-covered adjustment, framed as the additive emit-hook the kickoff sanctions).

## Correlation
Explicit `proposal_id` is preferred everywhere (thread it as harness tools already carry `engagement_id` /
endpoint). Best-effort endpoint match is the fallback and is deliberately conservative (unique match only).

## Behavior-identical proof obligation
Per harness: assert the returned `verdict` + `evidence_class` are byte-identical with and without the hook
active, while the funnel gains exactly one run per invocation.
