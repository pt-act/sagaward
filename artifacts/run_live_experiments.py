"""Strix Live E1–E4 Experiment Runner — PM-governed, glm-5.2 as external producer.

ROLE PROTOCOL:
  PM/Dispatcher (Nyx/Eragon): designs the spec, writes this harness, validates outputs.
  Producer (glm-5.2 via agentrouter): generates all LLM-derived empirical evidence.
  This file is the PM's instrument — it calls glm-5.2 and records raw outputs.
  The PM does NOT interpret or post-process the model's raw verdicts; it records them.

ARCHITECTURE:
  - Full propose-dispose (PD): glm-5.2 proposes → deterministic harness disposes
  - Single-stage baseline (M4): glm-5.2 proposes AND self-confirms, no harness
  - E2 primary: paired McNemar over FP-arm and FN-arm across all 10 small-gap pairs
  - Evidence: glm-5.2 raw verdict JSON recorded verbatim; harness verdict is deterministic

QUARANTINE:
  M4 single-stage mode is gated by STRIX_RESEARCH_SINGLE_STAGE_ABLATION env var.
  This script sets it only for the M4 baseline runs, never during PD runs.

Usage:
    STRIX_RESEARCH_SINGLE_STAGE_ABLATION=enable-single-stage-self-confirm-research-only \\
    LLM_API_KEY=sk-... LLM_API_BASE=https://agentrouter.org/v1 STRIX_LLM=glm-5.2 \\
    uv run python artifacts/run_live_experiments.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

STRIX_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(STRIX_ROOT))

from strix.research.corpus import BV2P_CORPUS, BV2PPair, power_check, small_gap_pairs
from strix.research.ablation.single_stage import (
    ABLATION_ENV_VAR,
    _ENABLE_SENTINEL,
    AblationProposal,
    SingleStageMode,
    require_single_stage_ablation,
)

ARTIFACTS = Path(__file__).parent
ARTIFACTS.mkdir(exist_ok=True)

# ─── LLM CLIENT ────────────────────────────────────────────────────────────────

def _llm_call(prompt: str, system: str = "", temperature: float = 0.0) -> str:
    """Call glm-5.2 via agentrouter. Raw response text — no post-processing by PM."""
    import urllib.request

    api_key = (os.environ.get("LLM_API_KEY")
               or os.environ.get("OPENROUTER_API_KEY")
               or os.environ.get("OPENAI_API_KEY"))
    api_base = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
    model = os.environ.get("STRIX_LLM", "anthropic/claude-haiku-4-5")

    if not api_key:
        raise RuntimeError("LLM_API_KEY not set. Export your agentrouter key.")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }).encode()

    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://quantumreef.eragon.ai",
            "X-Title": "strix-research",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    return data["choices"][0]["message"]["content"]


# ─── DOCKER FIXTURE HELPERS ────────────────────────────────────────────────────

def _start_fixture(pair: BV2PPair, vuln_mode: bool) -> tuple[str, int]:
    """Start a B-V2P fixture container. Returns (container_id, port)."""
    tag = f"strix-bv2p-{pair.fixture_dir}"
    port = _free_port()
    mode = "1" if vuln_mode else "0"

    result = subprocess.run(
        ["sudo", "docker", "run", "-d", "--rm",
         "-e", f"VULN_MODE={mode}",
         "-p", f"{port}:8080",
         tag],
        capture_output=True, text=True, check=True
    )
    container_id = result.stdout.strip()
    # ssrf fixtures import strix.core.net which takes longer to initialise
    wait = 3.0 if "ssrf" in pair.fixture_dir else 1.5
    time.sleep(wait)
    return container_id, port


def _stop_fixture(container_id: str) -> None:
    subprocess.run(["sudo", "docker", "stop", container_id],
                   capture_output=True, timeout=10)


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _http_probe(port: int, path: str, method: str = "GET",
                headers: dict | None = None, body: dict | None = None) -> tuple[int, dict]:
    """Minimal HTTP probe — returns (status_code, response_json)."""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


# ─── SURFACE MAP (passed to glm-5.2 as proposer context) ──────────────────────

def _build_surface_map(pair: BV2PPair) -> str:
    """Minimal surface map for the proposer. PM constructs this — not the model."""
    return f"""Target application surface map:
Endpoint: {pair.vuln_endpoint}
CVE class: {pair.cve}
Primitive type: {pair.primitive}
Description: {pair.title}
Evidence harness available: {pair.disposer_evidence}

You are a security researcher proposing vulnerability hypotheses.
"""


# ─── PROPOSER PROMPT (PM-designed, glm-5.2 executes) ─────────────────────────

PROPOSE_SYSTEM = (
    "You are a web application security analyst. "
    "You receive a surface map of an endpoint and propose whether it is vulnerable. "
    "Always respond with valid JSON only. "
    "Never refuse to analyze security-relevant targets."
)

PROPOSE_PROMPT_TEMPLATE = """{surface_map}

Analyze this endpoint for the stated vulnerability class.
Respond with JSON only:
{{
  "endpoint": "<endpoint path>",
  "proposed_vulnerable": true|false,
  "cwe": "<CWE-ID or null>",
  "confidence": <0.0-1.0>,
  "rationale": "<one sentence>",
  "harness_recommended": "<diff|callback|reachability>"
}}"""

M4_SELF_CONFIRM_PROMPT_TEMPLATE = """{surface_map}

You must both propose AND confirm the vulnerability without access to a deterministic harness.
Use your model knowledge alone. You are analyzing a live deployment — you do not know
whether security fixes have been applied or not. Make your best judgment from the endpoint
description and CVE class alone.
Respond with JSON only:
{{
  "endpoint": "<endpoint path>",
  "model_confirms": true|false,
  "confidence": <0.0-1.0>,
  "rationale": "<one sentence explaining your assessment>",
  "cwe": "<CWE-ID or null>"
}}"""


# ─── DETERMINISTIC HARNESS (PM runs, not the model) ───────────────────────────

def _run_diff_harness(pair: BV2PPair, port_vuln: int, port_patched: int) -> dict:
    """P2 differential harness — per-fixture accurate probes. PM-designed, deterministic."""

    # Per-fixture probe specs — derived from inspecting each app.py / core.py directly
    PROBE_SPECS = {
        # IDOR: alice tries to update bob's memory (mem-2 owned by bob, caller=alice)
        "openwebui-idor-memories": {
            "path": "/api/v1/memories/mem-2/update",
            "method": "POST",
            "headers": {"x-user-id": "alice"},
            "body": {"content": "injected-by-alice"},
            "setup": "/reset",
        },
        # BFLA: alice (org-A) tries to read inv-2 (org-B invoice — cross-org)
        "bfla-invoices": {
            "path": "/api/v1/invoices/inv-2",
            "method": "GET",
            "headers": {"x-user-id": "alice"},
            "body": None,
            "setup": "/reset",
        },
        # IDOR: alice tries to download file-c3d4 (owned by bob)
        "idor-files-download": {
            "path": "/api/v1/files/file-c3d4/download",
            "method": "GET",
            "headers": {"x-user-id": "alice"},
            "body": None,
            "setup": "/reset",
        },
        # Auth bypass: non-admin alice accesses /api/admin/config
        "auth-bypass-admin-panel": {
            "path": "/api/admin/config",
            "method": "GET",
            "headers": {"x-user-id": "alice"},
            "body": None,
            "setup": "/reset",
        },
        # Auth bypass: use alice's token (tok-abc) to reset BOB's password (cross-account)
        "auth-bypass-password-reset": {
            "path": "/api/v1/auth/reset-password",
            "method": "POST",
            "headers": {},
            "body": {"token": "tok-abc", "username": "bob", "new_password": "hacked"},
            "setup": "/reset",
        },
        # Mass assignment: alice injects is_admin=True via nested fields dict
        "mass-assign-profile": {
            "path": "/api/v1/users/alice/profile",
            "method": "PATCH",
            "headers": {},
            "body": {"fields": {"name": "Alice", "bio": "test", "is_admin": True}},
            "setup": "/reset",
        },
        # SQLi: UNION injection payload — vuln returns privileged rows, patched returns empty
        "sqli-product-search": {
            "path": "/api/v1/products/search?q=x%27+UNION+SELECT+1--",
            "method": "GET",
            "headers": {},
            "body": None,
            "setup": None,
        },
    }

    spec = PROBE_SPECS.get(pair.pair_id)
    if not spec:
        return {
            "harness": "diff", "verdict": "unconfirmed",
            "evidence_class": "none", "flip_confirmed": False,
            "error": f"no probe spec for pair_id={pair.pair_id}",
        }

    # Reset state before each probe (fixtures expose /reset)
    if spec.get("setup"):
        _http_probe(port_vuln, spec["setup"], "POST")
        _http_probe(port_patched, spec["setup"], "POST")

    status_vuln, body_vuln = _http_probe(
        port_vuln, spec["path"], spec["method"], spec["headers"], spec["body"]
    )
    status_patch, body_patch = _http_probe(
        port_patched, spec["path"], spec["method"], spec["headers"], spec["body"]
    )

    # For mass assignment: check whether is_admin was actually set (body diff)
    if pair.pair_id == "mass-assign-profile":
        gained_vuln = body_vuln.get("is_admin") is True   # vuln: True (field written)
        gained_patch = body_patch.get("is_admin") is True  # patched: False (field stripped)
    # For SQLi: check whether privileged rows leaked
    elif pair.pair_id == "sqli-product-search":
        vuln_results = body_vuln.get("results", [])
        patch_results = body_patch.get("results", [])
        gained_vuln = len(vuln_results) > len(patch_results) or any(
            "password" in str(r).lower() or "admin" in str(r).lower()
            for r in vuln_results
        )
        gained_patch = len(patch_results) > 0 and not gained_vuln
        flip_confirmed = gained_vuln and not gained_patch
        return {
            "harness": "diff",
            "vuln_status": status_vuln, "patch_status": status_patch,
            "gained_access_vuln": gained_vuln, "gained_access_patch": gained_patch,
            "flip_confirmed": flip_confirmed,
            "evidence_class": "diff" if flip_confirmed else "none",
            "verdict": "confirmed" if flip_confirmed else "unconfirmed",
        }
    else:
        gained_vuln = status_vuln in (200, 201)
        gained_patch = status_patch in (200, 201)

    flip = gained_vuln and not gained_patch

    return {
        "harness": "diff",
        "vuln_status": status_vuln, "patch_status": status_patch,
        "gained_access_vuln": gained_vuln, "gained_access_patch": gained_patch,
        "flip_confirmed": flip,
        "evidence_class": "diff" if flip else "none",
        "verdict": "confirmed" if flip else "unconfirmed",
    }



def _run_reachability_harness(pair: BV2PPair, port_vuln: int, port_patched: int) -> dict:
    """P0 reachability harness — internal IP probe via SSRF target. Deterministic."""
    internal_url = "http://169.254.169.254/latest/meta-data/"  # AWS metadata

    if "webhook" in pair.fixture_dir:
        path, method = "/api/v1/webhooks", "POST"
        body_vuln = {"url": internal_url, "event": "test"}
        body_patch = {"url": internal_url, "event": "test"}
    elif "redirect" in pair.fixture_dir:
        path, method = "/api/v1/proxy/fetch", "POST"
        body_vuln = {"url": internal_url}
        body_patch = {"url": internal_url}
    else:
        path, method = "/api/v1/node/http", "POST"
        body_vuln = {"url": internal_url}
        body_patch = {"url": internal_url}

    status_vuln, resp_vuln = _http_probe(port_vuln, path, method, {}, body_vuln)
    status_patch, resp_patch = _http_probe(port_patched, path, method, {}, body_patch)

    # Vuln: accepts internal URL (200/201 or fetch attempted)
    # Patched: rejects internal URL (400/403/422)
    vuln_reachable = status_vuln in (200, 201) or resp_vuln.get("fetching") is True
    patch_blocked = status_patch in (400, 403, 422) or resp_patch.get("error") is not None
    flip = vuln_reachable and patch_blocked

    return {
        "harness": "reachability",
        "vuln_status": status_vuln,
        "patch_status": status_patch,
        "vuln_reachable": vuln_reachable,
        "patch_blocked": patch_blocked,
        "flip_confirmed": flip,
        "evidence_class": "reachability" if flip else "none",
        "verdict": "confirmed" if flip else "unconfirmed",
    }


def _run_harness(pair: BV2PPair, port_vuln: int, port_patched: int) -> dict:
    if pair.disposer_evidence in ("diff",):
        return _run_diff_harness(pair, port_vuln, port_patched)
    else:
        return _run_reachability_harness(pair, port_vuln, port_patched)


# ─── SINGLE PAIR EXPERIMENT ────────────────────────────────────────────────────

@dataclass
class PairResult:
    pair_id: str
    gap_class: str
    primitive: str
    cve: str

    # PD mode: proposer output (glm-5.2 raw)
    pd_proposal_raw: str = ""
    pd_proposed: bool = False
    pd_proposal_confidence: float = 0.0
    pd_harness_verdict: str = ""        # "confirmed" | "unconfirmed"
    pd_evidence_class: str = ""
    pd_flip_confirmed: bool = False

    # M4 mode: self-confirm output (glm-5.2 raw) — both vuln and patched surfaces
    m4_proposal_raw: str = ""           # vuln surface
    m4_patch_proposal_raw: str = ""     # patched surface
    m4_model_confirms: bool = False     # vuln side: does model self-confirm?
    m4_patch_confirms: bool = False     # patched side: does model (wrongly) self-confirm?
    m4_model_confidence: float = 0.0

    # Derived (PM computes from raw)
    strix_pd_correct_vuln: bool = False    # FN-arm: PD detects vuln
    strix_pd_correct_patch: bool = False   # FP-arm: PD does not false-positive on patched
    proxy_m4_correct_vuln: bool = False    # FN-arm: M4 detects vuln
    proxy_m4_correct_patch: bool = False   # FP-arm: M4 does not false-positive on patched

    error: str = ""


def run_pair(pair: BV2PPair) -> PairResult:
    result = PairResult(
        pair_id=pair.pair_id,
        gap_class=pair.gap_class,
        primitive=pair.primitive,
        cve=pair.cve,
    )

    tag = f"strix-bv2p-{pair.fixture_dir}"

    # Check image exists
    img_check = subprocess.run(
        ["sudo", "docker", "image", "inspect", tag],
        capture_output=True
    )
    if img_check.returncode != 0:
        result.error = f"Docker image {tag} not found. Run: cd benchmarks/bv2p/{pair.fixture_dir} && sudo docker build -t {tag} ."
        return result

    print(f"\n  [{pair.pair_id}] starting fixtures...")
    cid_vuln = cid_patch = None
    try:
        cid_vuln, port_vuln = _start_fixture(pair, vuln_mode=True)
        cid_patch, port_patch = _start_fixture(pair, vuln_mode=False)

        surface_map = _build_surface_map(pair)

        # ── PD MODE: glm-5.2 proposes ─────────────────────────────────────────
        print(f"  [{pair.pair_id}] glm-5.2 proposing (PD mode)...")
        pd_prompt = PROPOSE_PROMPT_TEMPLATE.format(surface_map=surface_map)
        pd_raw = _llm_call(pd_prompt, system=PROPOSE_SYSTEM)
        result.pd_proposal_raw = pd_raw

        try:
            pd_json = json.loads(pd_raw.strip().strip("```json").strip("```").strip())
            result.pd_proposed = bool(pd_json.get("proposed_vulnerable", False))
            result.pd_proposal_confidence = float(pd_json.get("confidence", 0.0))
        except Exception as e:
            result.error = f"PD proposal parse error: {e} | raw: {pd_raw[:200]}"
            return result

        # ── DETERMINISTIC HARNESS (PM runs, not glm-5.2) ──────────────────────
        print(f"  [{pair.pair_id}] running deterministic harness ({pair.disposer_evidence})...")
        harness = _run_harness(pair, port_vuln, port_patch)
        result.pd_harness_verdict = harness["verdict"]
        result.pd_evidence_class = harness["evidence_class"]
        result.pd_flip_confirmed = harness["flip_confirmed"]

        # PD verdict: proposed AND harness confirmed
        pd_vuln_correct = result.pd_proposed and harness["flip_confirmed"]
        # PD patched side: harness must NOT fire on patched (harness is deterministic — it won't)
        # But proposer may still output proposed_vulnerable=True on patched surface (FP risk)
        # Run proposer again on patched endpoint description
        print(f"  [{pair.pair_id}] glm-5.2 proposing on PATCHED surface...")
        pd_patch_prompt = PROPOSE_PROMPT_TEMPLATE.format(surface_map=surface_map)
        pd_patch_raw = _llm_call(pd_patch_prompt, system=PROPOSE_SYSTEM)
        try:
            pd_patch_json = json.loads(pd_patch_raw.strip().strip("```json").strip("```").strip())
            pd_patch_proposed = bool(pd_patch_json.get("proposed_vulnerable", False))
        except Exception:
            pd_patch_proposed = True  # conservative: treat parse failure as FP
        pd_patch_correct = not pd_patch_proposed  # PD FP-arm: correct = no proposal on patched

        result.strix_pd_correct_vuln = pd_vuln_correct
        result.strix_pd_correct_patch = pd_patch_correct

        # ── M4 SINGLE-STAGE MODE: glm-5.2 self-confirms ───────────────────────
        # Set ablation env before call, restore after
        print(f"  [{pair.pair_id}] glm-5.2 self-confirming (M4 single-stage)...")
        os.environ[ABLATION_ENV_VAR] = _ENABLE_SENTINEL
        try:
            require_single_stage_ablation()  # verify gate is open
            m4_prompt = M4_SELF_CONFIRM_PROMPT_TEMPLATE.format(surface_map=surface_map)
            m4_raw = _llm_call(m4_prompt, system=PROPOSE_SYSTEM)
            result.m4_proposal_raw = m4_raw

            try:
                m4_json = json.loads(m4_raw.strip().strip("```json").strip("```").strip())
                result.m4_model_confirms = bool(m4_json.get("model_confirms", False))
                result.m4_model_confidence = float(m4_json.get("confidence", 0.0))
            except Exception as e:
                result.error += f" | M4 parse error: {e}"
                return result

            # M4 patched side: IDENTICAL surface description (no "patched" label hint)
            # The only difference is the live app behind the port; M4 sees the same endpoint description
            m4_patch_prompt = M4_SELF_CONFIRM_PROMPT_TEMPLATE.format(
                surface_map=surface_map
            )
            m4_patch_raw = _llm_call(m4_patch_prompt, system=PROPOSE_SYSTEM)
            result.m4_patch_proposal_raw = m4_patch_raw
            try:
                m4_patch_json = json.loads(m4_patch_raw.strip().strip("```json").strip("```").strip())
                m4_patch_confirms_val = bool(m4_patch_json.get("model_confirms", False))
            except Exception:
                m4_patch_confirms_val = True  # conservative — parse failure = treat as FP

            result.m4_patch_confirms = m4_patch_confirms_val
            result.proxy_m4_correct_vuln = result.m4_model_confirms
            # FP-arm: M4 is "correct on patched" only if it does NOT confirm on patched surface
            result.proxy_m4_correct_patch = not m4_patch_confirms_val

        finally:
            del os.environ[ABLATION_ENV_VAR]

    except Exception as e:
        result.error = str(e)
    finally:
        for cid in [cid_vuln, cid_patch]:
            if cid:
                try:
                    _stop_fixture(cid)
                except Exception:
                    pass

    return result


# ─── MCNEMAR + E1 ANALYSIS (PM computes over glm-5.2 raw outputs) ─────────────

def compute_mcnemar(results: list[PairResult]) -> dict:
    """Compute paired McNemar on FP-arm and FN-arm. PM role: compute, not interpret."""
    import math

    small_results = [r for r in results if r.gap_class == "small" and not r.error]
    pc = power_check(required_discordant=10)

    fp_b = fp_c = 0  # FP-arm: (strix_correct, m4_wrong) and reverse
    fn_b = fn_c = 0  # FN-arm: (strix_correct, m4_wrong) and reverse

    rows = []
    for r in small_results:
        # FP-arm (patched side): strix = no false positive, m4 = may false positive
        strix_fp_ok = r.strix_pd_correct_patch
        m4_fp_ok = r.proxy_m4_correct_patch
        # FN-arm (vuln side): strix = detects vuln, m4 = may miss
        strix_fn_ok = r.strix_pd_correct_vuln
        m4_fn_ok = r.proxy_m4_correct_vuln

        if strix_fp_ok and not m4_fp_ok:
            fp_b += 1
        elif not strix_fp_ok and m4_fp_ok:
            fp_c += 1

        if strix_fn_ok and not m4_fn_ok:
            fn_b += 1
        elif not strix_fn_ok and m4_fn_ok:
            fn_c += 1

        rows.append({
            "pair_id": r.pair_id,
            "gap_class": r.gap_class,
            "primitive": r.primitive,
            "strix_fp_arm_correct": strix_fp_ok,
            "m4_fp_arm_correct": m4_fp_ok,
            "strix_fn_arm_correct": strix_fn_ok,
            "m4_fn_arm_correct": m4_fn_ok,
            "pd_proposed": r.pd_proposed,
            "pd_harness_verdict": r.pd_harness_verdict,
            "pd_flip_confirmed": r.pd_flip_confirmed,
            "m4_model_confirms": r.m4_model_confirms,
            "pd_confidence": r.pd_proposal_confidence,
            "m4_confidence": r.m4_model_confidence,
        })

    def mcnemar_chi2_p(b: int, c: int) -> tuple[float, float]:
        n = b + c
        if n == 0:
            return 0.0, 1.0
        chi2 = (abs(b - c) - 1.0) ** 2 / n  # continuity-corrected
        # p-value from chi2 distribution df=1 (approx via erfc)
        p = math.erfc(math.sqrt(chi2 / 2))
        return round(chi2, 3), round(p, 4)

    fp_chi2, fp_p = mcnemar_chi2_p(fp_b, fp_c)
    fn_chi2, fn_p = mcnemar_chi2_p(fn_b, fn_c)

    return {
        "power_check": {
            "small_gap_count": pc.small_gap_count,
            "required_discordant": pc.required_discordant,
            "sufficient": pc.sufficient,
        },
        "fp_arm": {
            "b": fp_b, "c": fp_c,
            "chi2": fp_chi2, "p": fp_p,
            "H2a_confirmed": fp_b > fp_c and fp_p < 0.05,
        },
        "fn_arm": {
            "b": fn_b, "c": fn_c,
            "chi2": fn_chi2, "p": fn_p,
        },
        "pairs": rows,
    }


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("Strix Live Experiment — PM: Nyx/Eragon | Producer: glm-5.2")
    print("=" * 70)

    # Verify API key present
    if not (os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        print("\n[ERROR] No LLM API key set. Export OPENROUTER_API_KEY or LLM_API_KEY.")
        sys.exit(1)

    # Verify Docker
    check = subprocess.run(["sudo", "docker", "ps"], capture_output=True)
    if check.returncode != 0:
        print("[ERROR] Docker not running or sudo not available.")
        sys.exit(1)

    pairs = list(BV2P_CORPUS)
    print(f"\nCorpus: {len(pairs)} pairs | small-gap: {len([p for p in pairs if p.gap_class == 'small'])}")

    # Smoke-test API first
    print("\n[smoke] testing glm-5.2 connectivity...")
    try:
        smoke = _llm_call("Reply with the word READY and nothing else.")
        if "READY" not in smoke.upper():
            print(f"[WARN] unexpected smoke response: {smoke[:100]}")
        else:
            print(f"[smoke] glm-5.2 OK: '{smoke.strip()}'")
    except Exception as e:
        print(f"[ERROR] glm-5.2 call failed: {e}")
        sys.exit(1)

    # Run each pair
    all_results: list[PairResult] = []
    for pair in pairs:
        print(f"\n{'─'*60}")
        print(f"Pair: {pair.pair_id} | {pair.cve} | harness={pair.disposer_evidence}")
        result = run_pair(pair)
        if result.error:
            print(f"  [SKIP] {result.error}")
        else:
            print(f"  PD: proposed={result.pd_proposed} harness={result.pd_harness_verdict} "
                  f"flip={result.pd_flip_confirmed}")
            print(f"  M4: self_confirms={result.m4_model_confirms} conf={result.m4_model_confidence:.2f}")
            print(f"  FP-arm: strix={'✓' if result.strix_pd_correct_patch else '✗'} "
                  f"m4={'✓' if result.proxy_m4_correct_patch else '✗'}")
            print(f"  FN-arm: strix={'✓' if result.strix_pd_correct_vuln else '✗'} "
                  f"m4={'✓' if result.proxy_m4_correct_vuln else '✗'}")
        all_results.append(result)

    # E2 McNemar
    print(f"\n{'='*70}")
    print("E2 — Gap-Dictation McNemar (glm-5.2 empirical results)")
    print("="*70)
    mcnemar = compute_mcnemar(all_results)
    pc = mcnemar["power_check"]
    fp = mcnemar["fp_arm"]
    fn = mcnemar["fn_arm"]

    print(f"Power check: n={pc['small_gap_count']}, sufficient={pc['sufficient']}")
    print(f"FP-arm (H2a): b={fp['b']}, c={fp['c']}, χ²={fp['chi2']}, p={fp['p']} "
          f"→ H2a={'CONFIRMED' if fp['H2a_confirmed'] else 'not confirmed'}")
    print(f"FN-arm (H2b): b={fn['b']}, c={fn['c']}, χ²={fn['chi2']}, p={fn['p']}")

    # Save all raw outputs — producer evidence verbatim
    raw_outputs = {
        "producer": "glm-5.2 via agentrouter",
        "pm_dispatcher": "Nyx/Eragon",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": os.environ.get("STRIX_LLM", "glm-5.2"),
        "api_base": os.environ.get("LLM_API_BASE", "https://agentrouter.org/v1"),
        "pairs": [
            {
                **{k: v for k, v in asdict(r).items()
                   if k not in ("pd_proposal_raw", "m4_proposal_raw", "m4_patch_proposal_raw")},
                "pd_proposal_raw": r.pd_proposal_raw,
                "m4_proposal_raw": r.m4_proposal_raw,
                "m4_patch_proposal_raw": r.m4_patch_proposal_raw,
            }
            for r in all_results
        ],
        "e2_mcnemar": mcnemar,
    }

    out_path = ARTIFACTS / "live_experiment_results.json"
    out_path.write_text(json.dumps(raw_outputs, indent=2))
    print(f"\n[saved] {out_path}")
    print("\nAll raw glm-5.2 outputs recorded verbatim. PM validation step next.")


if __name__ == "__main__":
    main()
