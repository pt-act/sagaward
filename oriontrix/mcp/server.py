"""Oriontrix MCP server — raw JSON-RPC 2.0 over stdio.

Wraps the oriontrix bounty-grade engine for the triangle integration.
Implements: initialize, tools/list, tools/call (five tools).

Invariants preserved:
  I1 C⊆P  — only engine output surfaced
  I2      — harness_confirmed / evidence_class stripped from MCP input
  I3      — impact gate always on
  I4      — funnel completeness via existing funnel_emit/record_harness_run
  I5      — fail-closed on Docker down
  I6      — no capability curation (_BASE_TOOLS untouched)
  I7      — two-tier model preserved
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engagement registry (in-process, keyed by engagement_id)
# ---------------------------------------------------------------------------

_engagements: dict[str, dict[str, Any]] = {}

# Fields that callers must NEVER be able to inject (I2)
_STRIPPED_FIELDS = frozenset({"harness_confirmed", "evidence_class"})


# ---------------------------------------------------------------------------
# Docker health check (I5 — fail-closed)
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    """Check that Docker daemon is reachable. Fail-closed: any error → False."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------

def _build_scope_entries(target_url: str) -> list[str]:
    """Build scope entries from a target URL: exact host + wildcard subdomains."""
    parsed = urlparse(target_url if "://" in target_url else f"https://{target_url}")
    host = (parsed.hostname or target_url).lower().strip()
    return [host, f"*.{host}"]


def _strip_injection_fields(params: dict[str, Any]) -> dict[str, Any]:
    """Strip I2-violating fields from any MCP input dict. Returns cleaned copy."""
    return {k: v for k, v in params.items() if k not in _STRIPPED_FIELDS}


# ---------------------------------------------------------------------------
# Tool: oriontrix_run_engagement
# ---------------------------------------------------------------------------

async def _tool_run_engagement(params: dict[str, Any]) -> dict[str, Any]:
    """Launch a headless oriontrix engagement. Returns immediately with engagement_id."""
    params = _strip_injection_fields(params)

    target = params.get("target")
    if not target or not isinstance(target, str) or not target.strip():
        return {"error": "target is required and must be a non-empty string"}

    target = target.strip()

    # I5: Docker must be available
    if not _docker_available():
        return {
            "error": "Docker daemon is not available. Fail-closed: cannot start engagement.",
            "docker_available": False,
        }

    # Scope validation via decide()
    from oriontrix.core.govern.scope import (
        ActionClass,
        Target as ScopeTarget,
        Verdict,
        load_scope,
        decide,
    )

    scope_entries = _build_scope_entries(target)
    ctx = load_scope(scope_entries)
    parsed = urlparse(target if "://" in target else f"https://{target}")
    host = (parsed.hostname or target).lower().strip()
    decision = decide(ScopeTarget(host=host, action_class=ActionClass.HTTP), ctx)

    if decision.verdict != Verdict.ALLOW:
        return {
            "error": f"Target out of scope: {decision.reason}",
            "verdict": decision.verdict.value,
        }

    engagement_id = params.get("engagement_id") or f"eng-{uuid.uuid4().hex[:12]}"
    scan_mode = params.get("scan_mode", "standard")
    instruction = params.get("instruction", "")
    producer_model = params.get("producer_model")

    # Build run directory
    from oriontrix.core.paths import run_dir_for

    run_dir = run_dir_for(engagement_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone.utc)
    record = {
        "engagement_id": engagement_id,
        "status": "running",
        "target": target,
        "scope_entries": scope_entries,
        "scan_mode": scan_mode,
        "instruction": instruction,
        "producer_model": producer_model,
        "started_at": now.isoformat(),
        "run_dir": str(run_dir),
        "findings_so_far": 0,
        "funnel_runs": 0,
        "scope_refusals": 0,
        "last_event": "engagement_started",
        "error": None,
        "task": None,
    }
    _engagements[engagement_id] = record

    # Save engagement metadata to run_dir
    meta_path = run_dir / "engagement_meta.json"
    meta_path.write_text(json.dumps(record, default=str), encoding="utf-8")

    # Launch background task
    loop = asyncio.get_event_loop()
    task = loop.create_task(_run_engagement_task(engagement_id, target, scan_mode, instruction, producer_model))
    record["task"] = task

    return {
        "engagement_id": engagement_id,
        "status": "started",
        "run_dir": str(run_dir),
        "started_at": now.isoformat(),
    }


async def _run_engagement_task(
    engagement_id: str,
    target: str,
    scan_mode: str,
    instruction: str,
    producer_model: str | None,
) -> None:
    """Background task that runs the actual oriontrix scan."""
    record = _engagements.get(engagement_id)
    if record is None:
        return

    try:
        from oriontrix.core.runner import run_oriontrix_scan

        scan_config: dict[str, Any] = {
            "targets": [{"url": target, "type": "url"}],
            "scan_mode": scan_mode,
        }
        if instruction:
            scan_config["instruction"] = instruction

        # Determine image (use default oriontrix image)
        image = os.environ.get("ORIONTRIX_SANDBOX_IMAGE", "oriontrix-sandbox:latest")
        model = producer_model or os.environ.get("ORIONTRIX_LLM", "")

        record["last_event"] = "scan_running"

        await run_oriontrix_scan(
            scan_config=scan_config,
            scan_id=engagement_id,
            image=image,
            model=model if model else None,
            interactive=False,
        )

        record["status"] = "complete"
        record["last_event"] = "scan_complete"
        record["completed_at"] = datetime.now(tz=timezone.utc).isoformat()

    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        record["last_event"] = f"scan_failed: {exc}"
        record["failed_at"] = datetime.now(tz=timezone.utc).isoformat()
        logger.exception("Engagement %s failed", engagement_id)


# ---------------------------------------------------------------------------
# Tool: oriontrix_engagement_status
# ---------------------------------------------------------------------------

async def _tool_engagement_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return current status of an engagement."""
    params = _strip_injection_fields(params)
    engagement_id = params.get("engagement_id", "")
    if not engagement_id or engagement_id not in _engagements:
        return {"error": f"Unknown engagement_id: {engagement_id}"}

    record = _engagements[engagement_id]
    return {
        "engagement_id": engagement_id,
        "status": record["status"],
        "findings_so_far": record.get("findings_so_far", 0),
        "funnel_runs": record.get("funnel_runs", 0),
        "scope_refusals": record.get("scope_refusals", 0),
        "last_event": record.get("last_event"),
        "started_at": record.get("started_at"),
        "target": record.get("target"),
    }


# ---------------------------------------------------------------------------
# Tool: oriontrix_get_findings
# ---------------------------------------------------------------------------

async def _tool_get_findings(params: dict[str, Any]) -> dict[str, Any]:
    """Return findings from an engagement's run directory."""
    params = _strip_injection_fields(params)
    engagement_id = params.get("engagement_id", "")
    if not engagement_id or engagement_id not in _engagements:
        return {"error": f"Unknown engagement_id: {engagement_id}"}

    record = _engagements[engagement_id]
    run_dir = Path(record["run_dir"])

    # Look for vulnerabilities.json in run_dir
    vuln_path = run_dir / "vulnerabilities.json"
    if not vuln_path.exists():
        return {"engagement_id": engagement_id, "findings": [], "note": "No findings file yet"}

    try:
        vulns = json.loads(vuln_path.read_text(encoding="utf-8"))
        if isinstance(vulns, list):
            findings = vulns
        elif isinstance(vulns, dict):
            findings = vulns.get("vulnerabilities", [])
        else:
            findings = []

        # I1/I3: Only harness-confirmed findings with evidence_class != "none"
        confirmed = []
        unconfirmed = []
        for f in findings:
            ev = f.get("evidence_class", "none")
            if ev != "none":
                confirmed.append(f)
            else:
                unconfirmed.append(f)

        return {
            "engagement_id": engagement_id,
            "confirmed_findings": confirmed,
            "unconfirmed_count": len(unconfirmed),
            "total_raw": len(findings),
        }
    except Exception as exc:
        return {"engagement_id": engagement_id, "error": f"Failed to read findings: {exc}"}


# ---------------------------------------------------------------------------
# Tool: oriontrix_get_funnel
# ---------------------------------------------------------------------------

async def _tool_get_funnel(params: dict[str, Any]) -> dict[str, Any]:
    """Return funnel metrics for an engagement."""
    params = _strip_injection_fields(params)
    engagement_id = params.get("engagement_id", "")
    if not engagement_id or engagement_id not in _engagements:
        return {"error": f"Unknown engagement_id: {engagement_id}"}

    record = _engagements[engagement_id]
    run_dir = Path(record["run_dir"])

    funnel_path = run_dir / ".state" / "funnel.json"
    if not funnel_path.exists():
        return {"engagement_id": engagement_id, "funnel": None, "note": "No funnel data yet"}

    try:
        from oriontrix.research.metrics import load_funnel, summarize_funnel
        from oriontrix.research.corpus import ground_truth_labels

        funnel_log = load_funnel(funnel_path)
        records = funnel_log.list_records()
        labels = ground_truth_labels()
        summary = summarize_funnel(records, labels)

        return {
            "engagement_id": engagement_id,
            "funnel": summary.as_dict(),
        }
    except Exception as exc:
        return {"engagement_id": engagement_id, "error": f"Failed to compute funnel: {exc}"}


# ---------------------------------------------------------------------------
# Tool: oriontrix_corpus_status
# ---------------------------------------------------------------------------

async def _tool_corpus_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return corpus status — static data from the B-V2P corpus registry."""
    # I2: strip any injected fields even though this tool takes no meaningful input
    _ = _strip_injection_fields(params)

    from oriontrix.research.corpus import BV2P_CORPUS, ground_truth_labels
    from oriontrix.agents.factory import _BASE_TOOLS

    pairs = BV2P_CORPUS
    total = len(pairs)
    # Taxonomy (per PM NVD verification corpus-cve-verification.md, 2026-08-03):
    # Two ORTHOGONAL axes — vuln provenance (is_real_cve) and patch provenance (synthesized_patch).
    # 5 genuine public CVEs (is_real_cve=True) / 8 synthetic-pattern fixtures (is_real_cve=False).
    # 4 real upstream patches / 9 synthesized minimal-diff patches.
    # The 8 synthetic pairs carry `pattern:CVE-X` and do NOT reproduce those CVEs.
    public_cve = sum(1 for p in pairs if p.is_real_cve)
    synthetic = sum(1 for p in pairs if not p.is_real_cve)
    real_patch = sum(1 for p in pairs if not p.synthesized_patch)
    synthesized_patch = sum(1 for p in pairs if p.synthesized_patch)

    # Harness capabilities from disposer evidence types in corpus
    harness_caps = sorted(set(p.disposer_evidence for p in pairs))
    # Native capabilities = all tool names from _BASE_TOOLS (I6: no curation)
    native_caps = [t.name for t in _BASE_TOOLS]

    # Corpus hash for integrity
    corpus_str = json.dumps(
        [{"id": p.pair_id, "cve": p.cve, "ep": p.vuln_endpoint} for p in pairs],
        sort_keys=True,
    )
    corpus_hash = hashlib.sha256(corpus_str.encode()).hexdigest()[:16]

    return {
        "pairs": total,
        "public_cve_count": public_cve,
        "synthetic_count": synthetic,
        "real_patch_count": real_patch,
        "synthesized_patch_count": synthesized_patch,
        "harness_capabilities": harness_caps,
        "native_capabilities": native_caps,
        "native_capabilities_count": len(native_caps),
        "impact_gate": "on",
        "corpus_hash": corpus_hash,
    }


# ---------------------------------------------------------------------------
# JSON-RPC tool registry
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "oriontrix_run_engagement",
        "description": (
            "Launch a headless oriontrix security engagement against a target URL. "
            "Returns immediately with an engagement_id for async polling."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL to scan"},
                "scope_mode": {"type": "string", "description": "Scope mode (default: auto)"},
                "scan_mode": {
                    "type": "string",
                    "enum": ["quick", "standard"],
                    "description": "Scan depth",
                },
                "instruction": {"type": "string", "description": "Custom instruction for the agent"},
                "engagement_id": {"type": "string", "description": "Optional custom engagement ID"},
                "producer_model": {"type": "string", "description": "LLM model for the engagement"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "oriontrix_engagement_status",
        "description": "Get the current status of a running or completed engagement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "Engagement ID to query"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "oriontrix_get_findings",
        "description": (
            "Retrieve findings from a completed engagement. "
            "Only harness-confirmed findings (evidence_class != 'none') appear as confirmed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "Engagement ID"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "oriontrix_get_funnel",
        "description": "Get funnel metrics (R_prop, Prec_gate, R_e2e, funnel_efficiency) for an engagement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "Engagement ID"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "oriontrix_corpus_status",
        "description": (
            "Return B-V2P benchmark corpus status: pair count, CVE breakdown, "
            "harness capabilities, native tool count, and impact gate status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

_TOOL_DISPATCH: dict[str, Any] = {
    "oriontrix_run_engagement": _tool_run_engagement,
    "oriontrix_engagement_status": _tool_engagement_status,
    "oriontrix_get_findings": _tool_get_findings,
    "oriontrix_get_funnel": _tool_get_funnel,
    "oriontrix_corpus_status": _tool_corpus_status,
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 handler
# ---------------------------------------------------------------------------

async def handle_jsonrpc(request: dict[str, Any]) -> dict[str, Any]:
    """Process a single JSON-RPC 2.0 request and return a response."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    def _ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _err(code: int, message: str, data: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": error}

    # --- MCP lifecycle ---
    if method == "initialize":
        return _ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "oriontrix", "version": "0.1.0"},
        })

    if method == "notifications/initialized":
        # Client acknowledgement — no response needed for notifications
        return _ok(None)

    if method == "tools/list":
        return _ok({"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in _TOOL_DISPATCH:
            return _err(-32601, f"Unknown tool: {tool_name}")

        # I2: strip injection fields from all tool arguments
        tool_args = _strip_injection_fields(tool_args)

        try:
            result = await _TOOL_DISPATCH[tool_name](tool_args)
            return _ok({
                "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": "error" in result,
            })
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return _ok({
                "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                "isError": True,
            })

    return _err(-32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# stdio event loop
# ---------------------------------------------------------------------------

async def _async_main() -> None:
    """Read JSON-RPC requests from stdin, dispatch, write responses to stdout."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    # We need a lock for stdout to prevent interleaved writes
    write_lock = asyncio.Lock()

    async def write_response(response: dict[str, Any]) -> None:
        async with write_lock:
            line = json.dumps(response) + "\n"
            sys.stdout.write(line)
            sys.stdout.flush()

    while True:
        line = await reader.readline()
        if not line:
            break  # EOF

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue

        try:
            request = json.loads(line_str)
        except json.JSONDecodeError as exc:
            await write_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            })
            continue

        if not isinstance(request, dict):
            await write_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: expected object"},
            })
            continue

        # Handle notification (no id) — process but don't respond
        if "id" not in request and request.get("method", "").startswith("notifications/"):
            try:
                await handle_jsonrpc(request)
            except Exception:
                pass
            continue

        response = await handle_jsonrpc(request)
        if response.get("result") is not None or response.get("error") is not None:
            await write_response(response)


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
