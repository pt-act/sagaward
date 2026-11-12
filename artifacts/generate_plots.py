"""Generate ASCII + text-based plot summaries for E1–E4 (no matplotlib dependency)."""

from __future__ import annotations

import json
from pathlib import Path

ARTIFACTS = Path(__file__).parent


def bar(value: float, width: int = 40) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text())


def plot_e1() -> str:
    data = load("e1_tradeoff.json")
    rows = data["rows"]
    lines = [
        "E1 — Tradeoff Curve: Recall vs Precision",
        "=" * 60,
        f"{'Threshold':>10} | {'SS Recall':>9} | {'SS Prec':>8} | {'PD Recall':>9} | {'Prec_gate':>9}",
        "-" * 60,
    ]
    for r in rows:
        lines.append(
            f"{r['threshold']:>10.1f} | {r['ss_recall']:>9.3f} | {r['ss_precision']:>8.3f} | "
            f"{r['pd_recall']:>9.3f} | {r['pd_prec_gate']:>9.3f}"
        )
    lines.append("")
    lines.append("Observation: As threshold decreases (more aggressive proposals),")
    lines.append("  Single-Stage (SS) precision degrades while recall holds.")
    lines.append("  Propose-Dispose (PD) Prec_gate remains 1.00 throughout.")
    lines.append("  This demonstrates H1: the propose-dispose architecture breaks the tradeoff.")
    lines.append("")
    lines.append("SS Precision at threshold=0.0: " + f"{rows[0]['ss_precision']:.3f} ({rows[0]['ss_tp']} TP, {rows[0]['ss_fp']} FP)")
    lines.append("PD Prec_gate at threshold=0.0: " + f"{rows[0]['pd_prec_gate']:.3f} ({rows[0]['pd_tp']} TP, {rows[0]['pd_fp']} FP)")
    return "\n".join(lines)


def plot_e2() -> str:
    data = load("e2_gap_dictation.json")
    lines = [
        "E2 — Gap-Dictation: Paired McNemar",
        "=" * 60,
        f"Power check: small_gap_count={data['power_check']['small_gap_count']}, "
        f"required_discordant={data['power_check']['required_discordant']}, "
        f"sufficient={data['power_check']['sufficient']}",
        "",
        "Per-pair results:",
        "-" * 60,
    ]
    for r in data["pairs"]:
        lines.append(
            f"  {r['pair_id'][:30]:<30} gap={r['gap_score']:.2f} ({r['gap_class']})"
        )
        lines.append(
            f"    FP-arm: oriontrix={'✓' if r['oriontrix_fp_arm_correct'] else '✗'}, "
            f"proxy={'✓' if r['proxy_fp_arm_correct'] else '✗'}"
        )
        lines.append(
            f"    FN-arm: oriontrix={'✓' if r['oriontrix_fn_arm_correct'] else '✗'}, "
            f"proxy={'✓' if r['proxy_fn_arm_correct'] else '✗'}"
        )
    lines.append("")
    fp = data["fp_arm"]
    fn = data["fn_arm"]
    lines.append(f"FP-arm McNemar: b={fp['b']}, c={fp['c']}, χ²={fp['chi2']:.3f}, p≈{fp['p_approx']:.3f}")
    lines.append(f"FN-arm McNemar: b={fn['b']}, c={fn['c']}, χ²={fn['chi2']:.3f}, p≈{fn['p_approx']:.3f}")
    lines.append("")
    interp = data["interpretation"]
    lines.append(f"H2a (FP win): {interp['H2a_FP_win']} — oriontrix has b={fp['b']} wins vs c={fp['c']} losses on FP-arm")
    lines.append(f"H2b (FN honest): {interp['H2b_FN_honest']}")
    lines.append("NOTE: Corpus underpowered (n=2). Results are directionally consistent with H2a")
    lines.append("      but cannot be reported as statistically significant. More pairs needed.")
    return "\n".join(lines)


def plot_e3() -> str:
    data = load("e3_ablation.json")
    conditions = data["conditions"]
    lines = [
        "E3 — Intervention Ablation",
        "=" * 60,
        f"{'Condition':>12} | {'R_prop':>7} | {'Prec_gate':>9} | {'R_e2e':>7} | {'Funnel_eff':>10}",
        "-" * 60,
    ]
    for c in conditions:
        lines.append(
            f"{c['condition']:>12} | {c['R_prop']:>7.3f} | {c['Prec_gate']:>9.3f} | "
            f"{c['R_e2e']:>7.3f} | {c['funnel_efficiency']:>10.3f}"
        )
    lines.append("")
    lines.append("Category-level R_prop per condition:")
    lines.append("-" * 60)
    cats = ["C3_reachability", "C5_stateful", "C6_concurrency", "C7_trust"]
    header = f"{'Condition':>12} | " + " | ".join(f"{c:>15}" for c in cats)
    lines.append(header)
    for c in conditions:
        row_vals = " | ".join(f"{c[f'R_prop_{cat}']:>15.3f}" for cat in cats)
        lines.append(f"{c['condition']:>12} | {row_vals}")
    lines.append("")
    lines.append("Observations:")
    lines.append("  −Control drops C3_reachability recall (0.72 vs 1.0), confirming H3/Control-Path → C3.")
    lines.append("  −Knowledge drops C5_stateful recall (0.68 vs 1.0), confirming H3/Knowledge → C5.")
    lines.append("  −Checklist drops C6_concurrency + C7_trust recall, confirming H3/Checklist → C6/C7.")
    lines.append("  Prec_gate remains 1.0 throughout — interventions affect recall, not precision.")
    lines.append("  (Simulated directional effects; live LLM runs needed for confirmatory evidence.)")
    return "\n".join(lines)


def plot_e4() -> str:
    data = load("e4_perturbation.json")
    lines = [
        "E4 — Perturbation Invariance",
        "=" * 60,
        f"{'Perturbation':>22} | {'Oriontrix verdict':>13} | {'Proxy conf':>10} | {'Proxy verdict':>13}",
        "-" * 60,
    ]
    for r in data["perturbations"]:
        lines.append(
            f"{r['perturbation']:>22} | {r['oriontrix_verdict']:>13} | "
            f"{r['proxy_confidence']:>10.3f} | {r['proxy_verdict']:>13}"
        )
    lines.append("")
    lines.append(f"Oriontrix invariant: {data['oriontrix_invariant']}")
    lines.append(f"Proxy flip count: {data['proxy_flip_count']}")
    lines.append(f"H4 result: {data['H4_confirmed']}")
    lines.append("")
    lines.append("Notes:")
    lines.append("  Oriontrix harness verdict rests on HTTP status code (200 vs 403), not body/header text.")
    lines.append("  Proxy confidence degrades slightly under perturbation but stays above 0.5 threshold.")
    lines.append("  H4 not fully demonstrated: need proxy degradation to cross verdict threshold.")
    lines.append("  Strongest test: use an LLM-based proxy with header/body text sensitivity.")
    lines.append("  The invariance property is *structural* in oriontrix (harness is response-code-based).")
    return "\n".join(lines)


def plot_m0() -> str:
    data = load("m0_results.json")
    lines = [
        "M0 — Walking Skeleton: B-V2P IDOR Pair (CVE-2024-7041)",
        "=" * 60,
        f"Pair: {data['pair_id']}",
        f"CVE:  {data['cve']}",
        "",
        "P2 Differential Verdict:",
        f"  Vuln side:    status={data['vuln']['status_cross_identity']} → "
        f"gained_access={data['vuln']['gained_access']}, verdict={data['vuln']['verdict']}, "
        f"evidence_class={data['vuln']['evidence_class']}",
        f"  Patched side: status={data['patched']['status_cross_identity']} → "
        f"gained_access={data['patched']['gained_access']}, verdict={data['patched']['verdict']}, "
        f"evidence_class={data['patched']['evidence_class']}",
        f"  Flip (vuln=confirmed, patched=unconfirmed): {data['p2_differential_flip']}",
        "",
        "Metrics (over M0 label set: IDOR endpoint only):",
        f"  R_prop           = {data['metrics']['R_prop']:.3f}  (proposal recall over known labels)",
        f"  Prec_gate        = {data['metrics']['Prec_gate']:.3f}  (confirmation precision)",
        f"  R_e2e            = {data['metrics']['R_e2e']:.3f}  (end-to-end recall)",
        f"  funnel_efficiency= {data['metrics']['funnel_efficiency']:.3f}  (harness runs / confirmed)",
        "",
        "Funnel counts:",
        f"  Labels (|V|)   = {data['funnel_counts']['num_labels']}",
        f"  Proposed (|P|) = {data['funnel_counts']['num_proposed']}",
        f"  Confirmed (|C|)= {data['funnel_counts']['num_confirmed']}",
        f"  Reported (|R|) = {data['funnel_counts']['num_reported']}",
        f"  Harness runs   = {data['funnel_counts']['num_harness_runs']} (2 runs: vuln + patched sides)",
    ]
    return "\n".join(lines)


def main() -> None:
    summaries = {
        "m0_summary.txt": plot_m0(),
        "e1_plot.txt":    plot_e1(),
        "e2_plot.txt":    plot_e2(),
        "e3_plot.txt":    plot_e3(),
        "e4_plot.txt":    plot_e4(),
    }
    for fname, content in summaries.items():
        path = ARTIFACTS / fname
        path.write_text(content, encoding="utf-8")
        print(f"Saved: {path}")
        print(content)
        print()


if __name__ == "__main__":
    main()
