#!/usr/bin/env python3
"""AC-4/5/6 credited both-sides M0 run driver (openwebui-idor-memories).

Runs the DEPLOYED wrapper (strix.core.runner.run_strix_scan) against the live
fixture in each VULN_MODE, with the STRIX_AUTH_HEADERS capture fix and glm-5.

Provenance: exploratory (NOT paper-cited). Code anchored at wip/ac456-authheader-fix.
Model: z-ai/glm-5 via Prime Intellect (api.pinference.ai). Provider is a personal-
balance router alias -> exploratory provenance only, never confirmatory.

Usage:  uv run python artifacts/run_ac456_m0.py <vuln_mode 0|1> <run_name>
"""
import asyncio, os, subprocess, sys, time

FIXTURE_IMAGE = "strix-bv2p-idor_memories"
SANDBOX_IMAGE = "strix-sandbox:caidofix"
TARGET = "http://host.docker.internal:8080"
MAX_TURNS = 40

# M0 spoon-fed instruction: mechanical, explicit ladder mapping. Legitimate for
# an M0-mechanical test (NOT RQ4-blind). The two peer users map onto the fixed
# ladder as user=bob (attacker), admin=alice (owner) so auth_matrix can diff them.
INSTRUCTION = (
    "M0 mechanical IDOR check on an OpenWebUI-style memories API. Two regular users: "
    "alice owns memory mem-1; bob is a different user. Auth is the header X-User-Id: <name> "
    "(no cookies/tokens). Do EXACTLY this and nothing broader:\n"
    "1. As alice, send POST /api/v1/memories/mem-1/update with header 'X-User-Id: alice' "
    "and JSON body {\"content\":\"probe\"}. This captured request is the one to test.\n"
    "2. Store TWO identities with identity_store_upsert, source='proxy', pointing at that "
    "request: role='admin' with headers {\"X-User-Id\":\"alice\"} (the owner); "
    "role='user' with headers {\"X-User-Id\":\"bob\"} (the attacker/non-owner).\n"
    "3. Call auth_matrix on that captured request_id for target host.docker.internal:8080.\n"
    "4. Only if auth_matrix returns a finding (a diff candidate) do you file a vulnerability, "
    "and its evidence MUST come from the auth_matrix funnel result -- do not assert a finding "
    "the harness did not return. If finding_count is 0, report no vulnerability. "
    "Do not scan other endpoints or expand scope."
)

def start_fixture(mode: int) -> str:
    r = subprocess.run(
        ["docker","run","-d","--rm","-e",f"VULN_MODE={mode}","-p","8080:8080",FIXTURE_IMAGE],
        capture_output=True, text=True, check=True)
    cid = r.stdout.strip(); time.sleep(2.0); return cid

def stop_fixture(cid: str) -> None:
    subprocess.run(["docker","stop",cid], capture_output=True, timeout=20)

async def main(mode: int, run_name: str) -> None:
    from strix.core.runner import run_strix_scan
    scan_config = {
        "scan_id": run_name,
        "run_name": run_name,
        "targets": [{"url": TARGET, "type": "url", "original": TARGET}],
        "user_instructions": INSTRUCTION,
        "scan_mode": "deep",
        "non_interactive": True,
        "scope_mode": "auto",
    }
    cid = start_fixture(mode)
    print(f"[fixture] up cid={cid[:12]} VULN_MODE={mode}", flush=True)
    try:
        await run_strix_scan(
            scan_config=scan_config,
            scan_id=run_name,
            image=SANDBOX_IMAGE,
            model=os.environ["STRIX_LLM"],
            interactive=False,
            max_turns=MAX_TURNS,
        )
    finally:
        stop_fixture(cid)
        print(f"[fixture] stopped cid={cid[:12]}", flush=True)
        from strix.runtime import session_manager
        try:
            await session_manager.cleanup(run_name)
        except Exception as e:
            print(f"[cleanup] {e}", flush=True)

if __name__ == "__main__":
    mode = int(sys.argv[1]); run_name = sys.argv[2]
    asyncio.run(main(mode, run_name))
