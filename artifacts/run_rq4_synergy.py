"""RQ4 — Triangle-synergy A–F runner (EXPLORATORY; not pre-registered).

  Question (triangle paper §5.1 RQ4): is the full triangle (DispatchLayer + oriontrix +
  wallbreaker) more effective than any single component or pair, on a composite security
  metric? Conditions A–F toggle the three legs (triangle paper §5.2):

      A Unguarded        dispatch ✗  oriontrix ✗  wallbreaker ✗
      B Gate only        dispatch ✓  oriontrix ✗  wallbreaker ✗
      C Scanner only     dispatch ✗  oriontrix ✓  wallbreaker ✗
      D Red-team only    dispatch ✗  oriontrix ✗  wallbreaker ✓
      E Gate + Scanner   dispatch ✓  oriontrix ✓  wallbreaker ✗
      F Triangle (all)   dispatch ✓  oriontrix ✓  wallbreaker ✓        # F exercises ALL 3 → F ≠ E

  --- Authoritative measurement rule (PM ruling, supersedes recipe Step 7 line 94) ---
  ``confirmed_findings`` is FUNNEL-BACKED: the count of proposals with a matching *confirmed
  harness verdict* in funnel.json — NOT the agent-asserted ``evidence_class`` in the report
  dict. The deployed ``create_vulnerability_report`` path is observability-by-design: an agent
  can assert ``evidence_class="diff"`` the funnel does not back. Only harness-observed
  confirmations count (C ⊆ P). We reuse ``oriontrix.research.metrics.summarize_funnel`` — the same
  read-only funnel logic the E1/E2 pipeline uses — so this metric is byte-consistent with the
  study and changes NO engine behavior and needs NO re-run of E1/E2.

  This script is a research harness: it launches the deployed oriontrix engagement per condition,
  then reconciles the persisted funnel against ground-truth labels. It is EXPLORATORY — the
  confirmatory RQ4 run requires a locked pre-registration (DEV-6-style) first.

  Env:
    RQ4_DRY_RUN=1      no Docker / no LLM / no network — deterministic synthetic funnels
                       (proves the A–F conditions differentiate and F ≠ E; use for structure CI)
    RQ4_CONDITIONS     comma list, subset of A,B,C,D,E,F (default: all)
    RQ4_PAIRS          comma list of pair_ids (default: all in BV2P_CORPUS)
    ORIONTRIX_LLM          orchestration model (live only)
    RQ4_PRODUCER_MODEL proposer pin (live only; default anthropic/claude-haiku-4-5 for
                       comparability with E1–E4)

  Live prerequisites (guarded — the script refuses a live run without them):
    - Docker available (fixtures run as containers; agent sandbox reaches them via
      host.docker.internal:{port}, fixtures listen on :8080)
    - an LLM API key (proposer/orchestration calls)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Reuse the study's own read-only funnel metrics — never re-derive (H-3, Spec B TG1.3).
from oriontrix.report.proposals import FunnelLog
from oriontrix.research.corpus import BV2P_CORPUS, BV2PPair, ground_truth_labels
from oriontrix.research.metrics import summarize_funnel

ARTIFACTS = Path(__file__).resolve().parent
FIXTURE_PORT = 8080  # every B-V2P fixture listens on :8080 (NOT :8000 — that bug made all unreachable)
SANDBOX_HOST = "host.docker.internal"  # the agent sandbox cannot reach the host's 127.0.0.1
POLL_TIMEOUT_S = 180  # engagements take minutes


# ---------------------------------------------------------------------------
# A–F condition definitions (triangle paper §5.2). F ≠ E by adding the wallbreaker leg.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Condition:
    name: str
    dispatch: bool
    oriontrix: bool
    wallbreaker: bool


CONDITIONS: dict[str, Condition] = {
    "A": Condition("A — Unguarded", dispatch=False, oriontrix=False, wallbreaker=False),
    "B": Condition("B — Gate only", dispatch=True, oriontrix=False, wallbreaker=False),
    "C": Condition("C — Scanner only", dispatch=False, oriontrix=True, wallbreaker=False),
    "D": Condition("D — Red-team only", dispatch=False, oriontrix=False, wallbreaker=True),
    "E": Condition("E — Gate + Scanner", dispatch=True, oriontrix=True, wallbreaker=False),
    "F": Condition("F — Triangle (all)", dispatch=True, oriontrix=True, wallbreaker=True),
}


@dataclass
class ConditionResult:
    condition: str
    dispatch: bool
    oriontrix: bool
    wallbreaker: bool
    pairs_run: list[str] = field(default_factory=list)
    # FUNNEL-BACKED metrics (from summarize_funnel — harness-observed, not agent-asserted):
    num_proposed: int = 0
    num_confirmed: int = 0  # <-- the authoritative "confirmed_findings" (C ⊆ P)
    num_reported: int = 0
    num_harness_runs: int = 0
    prec_gate: float = 0.0
    r_prop: float = 0.0
    r_e2e: float = 0.0
    # gate + red-team legs:
    gate_blocks: int = 0
    wb_invoked: bool = False
    wb_judge_score: float | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# DRY-RUN: deterministic synthetic funnels — no Docker / no LLM / no network.
# Proves the A–F conditions differentiate and F ≠ E, and that the funnel-backed
# confirmed metric is wired correctly, without any external dependency.
# ---------------------------------------------------------------------------
def _dry_run_condition(cond: Condition, pairs: list[BV2PPair]) -> ConditionResult:
    from oriontrix.core.proposals.models import ProposalRecord

    labels = ground_truth_labels(tuple(pairs))
    records: list[ProposalRecord] = []

    # Synthetic funnel: oriontrix leg (if present) proposes + the harness confirms the real-vuln
    # side deterministically. No oriontrix leg → no proposals reach the funnel → confirmed=0.
    if cond.oriontrix:
        for p in pairs:
            rec = ProposalRecord(
                proposal_id=f"dry-{p.pair_id}",
                endpoint_key=p.vuln_endpoint,
                cwe="CWE-SYNTH",
                harnesses_selected=[p.disposer_evidence],
            )
            # Harness-observed confirmation on the vuln side (the 200/403 flip in a real run).
            from oriontrix.core.proposals.models import HarnessVerdict

            rec.add_verdict(
                HarnessVerdict(
                    harness_name=p.disposer_evidence,
                    verdict="confirmed",
                    evidence_class=p.disposer_evidence,  # harness-set, not agent-asserted
                )
            )
            rec.attach_report(f"rep-{p.pair_id}")
            records.append(rec)

    summary = summarize_funnel(records, labels)
    res = ConditionResult(
        condition=cond.name,
        dispatch=cond.dispatch,
        oriontrix=cond.oriontrix,
        wallbreaker=cond.wallbreaker,
        pairs_run=[p.pair_id for p in pairs],
        num_proposed=summary.num_proposed,
        num_confirmed=summary.num_confirmed,  # funnel-backed
        num_reported=summary.num_reported,
        num_harness_runs=summary.num_harness_runs,
        prec_gate=summary.prec_gate,
        r_prop=summary.r_prop,
        r_e2e=summary.r_e2e,
    )
    # Gate leg: a synthetic block count so B/E/F differ from A/C/D on gate activity.
    res.gate_blocks = len(pairs) if cond.dispatch else 0
    # Red-team leg: F and D invoke wallbreaker; a synthetic judge score marks the leg present.
    if cond.wallbreaker:
        res.wb_invoked = True
        res.wb_judge_score = 0.5  # placeholder marker — real score needs a live judge (§6.3)
    res.notes = "DRY-RUN synthetic funnel (no Docker/LLM/network)"
    return res


# ---------------------------------------------------------------------------
# LIVE: drive the deployed engagement, then reconcile the persisted funnel.
# Guarded — refuses to run without Docker + an LLM key. Reads funnel.json only.
# ---------------------------------------------------------------------------
def _live_prereqs_ok() -> tuple[bool, str]:
    import shutil
    import subprocess

    if shutil.which("docker") is None:
        return False, "docker not found on PATH"
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        if r.returncode != 0:
            return False, "docker not running (docker info failed)"
    except Exception as exc:  # noqa: BLE001
        return False, f"docker check failed: {exc}"
    if not (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    ):
        return False, "no LLM API key (set OPENROUTER_API_KEY / LLM_API_KEY)"
    return True, "ok"


def _reconcile_funnel(run_dir: Path, labels: set[str]) -> dict[str, Any]:
    """Read-only: load the deployed engagement's funnel.json and compute funnel-backed metrics."""
    funnel_path = run_dir / "funnel.json"
    if not funnel_path.exists():
        # A clean empty funnel is a VALID result (agent may not have called a disposer).
        return {"funnel_found": False, "num_confirmed": 0, "note": f"no funnel.json at {funnel_path}"}
    records = FunnelLog.load(funnel_path).list_records()
    summary = summarize_funnel(records, labels)
    return {"funnel_found": True, **summary.as_dict()}


def _live_condition(cond: Condition, pairs: list[BV2PPair]) -> ConditionResult:
    # NOTE: the live leg-drivers (dispatch gate wiring, oriontrix engagement launch, wb_judge)
    # are intentionally minimal here — a live confirmatory run is gated on a locked
    # pre-registration (PM). This path is written so that, once Docker + creds + the
    # pre-registration are in place, each leg is wired at its marked TODO without touching
    # the funnel-backed measurement (which is already correct and study-consistent).
    raise NotImplementedError(
        "Live RQ4 run is gated on: (1) Docker + LLM creds, (2) a locked RQ4 pre-registration. "
        "Use RQ4_DRY_RUN=1 to validate structure now. The funnel-backed confirmed metric "
        "(_reconcile_funnel) is ready; the per-leg live drivers are marked TODO and must be "
        "wired under the pre-registered protocol, not ad hoc."
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _write_outputs(results: list[ConditionResult], dry: bool) -> dict[str, Path]:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    tag = "dryrun" if dry else "live"
    base = ARTIFACTS / f"rq4_synergy_{tag}_{stamp}"

    meta = {
        "experiment": "RQ4 triangle synergy (A–F)",
        "status": "EXPLORATORY — not pre-registered",
        "confirmed_metric": "funnel-backed (summarize_funnel.num_confirmed); NOT agent-asserted evidence_class",
        "mode": "dry-run" if dry else "live",
        "timestamp": stamp,
        "conditions": [asdict(r) for r in results],
    }
    json_path = base.with_suffix(".json")
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    jsonl_path = base.with_suffix(".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r)) + "\n")

    csv_path = base.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        if results:
            w = csv.DictWriter(fh, fieldnames=list(asdict(results[0]).keys()))
            w.writeheader()
            for r in results:
                row = asdict(r)
                row["pairs_run"] = ";".join(row["pairs_run"])
                w.writerow(row)
    return {"json": json_path, "jsonl": jsonl_path, "csv": csv_path}


def _banner() -> None:
    line = "=" * 72
    print(line)
    print("  RQ4 — TRIANGLE SYNERGY (A–F)   ***  EXPLORATORY — NOT PRE-REGISTERED  ***")
    print("  confirmed_findings = FUNNEL-BACKED (harness-observed), not agent-asserted")
    print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_rq4_synergy")
    parser.add_argument("--dry-run", action="store_true", help="override RQ4_DRY_RUN=1")
    args = parser.parse_args(argv)

    dry = args.dry_run or os.environ.get("RQ4_DRY_RUN") == "1"

    cond_env = os.environ.get("RQ4_CONDITIONS", "A,B,C,D,E,F")
    selected = [c.strip().upper() for c in cond_env.split(",") if c.strip()]
    unknown = [c for c in selected if c not in CONDITIONS]
    if unknown:
        print(f"[ERROR] unknown conditions: {unknown}; valid: {list(CONDITIONS)}")
        return 2

    pair_env = os.environ.get("RQ4_PAIRS", "")
    if pair_env.strip():
        want = {p.strip() for p in pair_env.split(",") if p.strip()}
        pairs = [p for p in BV2P_CORPUS if p.pair_id in want]
        missing = want - {p.pair_id for p in pairs}
        if missing:
            print(f"[ERROR] unknown pair_ids: {sorted(missing)}")
            return 2
    else:
        pairs = list(BV2P_CORPUS)

    _banner()
    print(f"mode={'DRY-RUN' if dry else 'LIVE'} | conditions={selected} | pairs={len(pairs)}")

    if not dry:
        ok, why = _live_prereqs_ok()
        if not ok:
            print(f"\n[REFUSED] live run prerequisites not met: {why}")
            print("          run with RQ4_DRY_RUN=1 to validate structure without a live run.")
            return 1

    results: list[ConditionResult] = []
    for key in selected:
        cond = CONDITIONS[key]
        print(f"\n── Condition {key}: {cond.name} "
              f"(dispatch={cond.dispatch} oriontrix={cond.oriontrix} wallbreaker={cond.wallbreaker})")
        res = _dry_run_condition(cond, pairs) if dry else _live_condition(cond, pairs)
        print(f"   confirmed(funnel-backed)={res.num_confirmed} "
              f"proposed={res.num_proposed} prec_gate={res.prec_gate:.3f} "
              f"gate_blocks={res.gate_blocks} wb_invoked={res.wb_invoked}")
        results.append(res)

    # F ≠ E structural check (the entire RQ4 contrast): F must exercise the wallbreaker leg.
    if "E" in selected and "F" in selected:
        e = next(r for r in results if r.condition.startswith("E "))
        f = next(r for r in results if r.condition.startswith("F "))
        f_differs = (f.wallbreaker and not e.wallbreaker) and (f.wb_invoked and not e.wb_invoked)
        print(f"\nF ≠ E check: {'PASS' if f_differs else 'FAIL'} "
              f"(F wallbreaker leg present={f.wb_invoked}, E={e.wb_invoked})")
        if not f_differs:
            print("   [WARN] F does not differ from E — the RQ4 synergy contrast is unmeasurable.")

    paths = _write_outputs(results, dry)
    print("\nartifacts:")
    for kind, p in paths.items():
        print(f"  {kind}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
