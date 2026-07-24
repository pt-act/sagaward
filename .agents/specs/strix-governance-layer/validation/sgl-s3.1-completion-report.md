# S3.1 Completion Report — Breaker measures target-request health, not agent-cycle health

**Spec:** strix-governance-layer (SGL-Core) · S3.1 deferred item from verdict-09/10  
**Branch:** `sgl-s3.1` @ `678e315`  
**Producer:** CLI (Opus routing per pm-decision-breaker-target-health.md)  
**Date:** 2026-06-21

---

## What S3.1 fixes

The circuit breaker previously measured **agent-cycle wall time** (recording `is_error=True` on every agent run exception, and `is_error=False` on success). This meant:
- A slow LLM response could trip the breaker even though the target was healthy.
- A target being down would only trip the breaker if the agent happened to crash.

S3.1 re-sources the breaker from the **actual target-request layer**:
- **Egress proxy** (inside container): records connection-level outcomes — TCP connect success/failure, timeout, reset.
- **Proxy tools** (`repeat_request`): records HTTP-level outcomes — 5xx, 429.
- **Agent loop** (`_poll_target_health`): polls a JSONL file written by the proxy, feeds events into the breaker.

The breaker now measures **target health**, not agent health.

---

## Changes (5 files, +173/-20)

### strix/core/execution.py (+88/-20)
- **Removed** agent-cycle `breaker.record()` calls from `_run_cycle` success (`else`) and error (`except`) paths.
- **Added** `_poll_target_health(coordinator, context)`:
  - Reads `/var/log/strix/target_health.jsonl` from the sandbox container via `docker_client.exec_read_file`.
  - Parses each JSONL line and calls `breaker.record(latency_ms=..., is_error=...)`.
  - Clears the file via `docker_client.exec_command(container_id, "truncate -s 0 ...")`.
  - Called at the top of both `run_agent_loop` (interactive) and `_run_noninteractive_until_lifecycle` (non-interactive), before the cost-ceiling check.
  - Best-effort: all exceptions swallowed, governance proceeds regardless.

### strix/core/runner.py (+1)
- Added `"docker_client": bundle["client"]` to the agent context dict so `_poll_target_health` can exec into the container.

### strix/runtime/docker_client.py (+23)
- Added `exec_read_file(container_id, path) -> str`: reads a file from inside a running container via `docker-py` `exec_run`.
- Added `exec_command(container_id, command) -> None`: fire-and-forget command exec.
- **Bug fix** (reviewer-found): `container.exec_run()` returns a tuple `(exit_code, output)`, not an object with `.exit_code` / `.output`. Fixed to proper tuple unpacking.

### strix/tools/proxy/tools.py (+43)
- Added `_record_target_health(ctx, *, latency_ms, is_error)` helper: extracts `coordinator.breaker` from context and calls `breaker.record()`.
- `repeat_request` success path: after replay, parses response status code. Records `is_error=True` for 5xx or 429; `is_error=False` otherwise.
- `repeat_request` error path: **narrowed** from blanket `except Exception` to `except (OSError, TimeoutError)` for target-health recording. Code bugs / Caido parse errors no longer falsely trip the breaker.
- Removed unused `EngagementCtx` import (F401 cleanup).

### strix/runtime/egress_proxy.py (+38)
- Added `_write_target_health_event(**fields)`: appends JSONL to `/var/log/strix/target_health.jsonl` inside the container. Best-effort (exceptions swallowed).
- `_handle_connection` success path: after `asyncio.open_connection` succeeds, records `is_error=False` with time-to-connect latency. Gives the breaker an accurate error-rate denominator.
- `_handle_connection` failure path: on `OSError` / `asyncio.TimeoutError`, records `is_error=True` with error type.
- Uses `await asyncio.to_thread(...)` for non-blocking writes from async handlers.

---

## Verification

### Test suite
```
$ uv run pytest tests/ -q
524 passed, 4 failed, 19 subtests passed (94.65s)
```
The 4 failures are the **pre-existing** `test_business_logic_fixture` Docker integration tests (PRE-1, fails identically on `main`). No new failures introduced.

### Ruff
```
$ uv run ruff check strix/core/execution.py strix/core/runner.py strix/runtime/docker_client.py strix/runtime/egress_proxy.py strix/tools/proxy/tools.py
36 errors, all pre-existing in the modified files. Zero new errors introduced by S3.1.
```

### Code review
Reviewer round 1 flagged two bugs:
1. `docker_client.py`: `exec_run` tuple-unpacking bug → **fixed**.
2. `egress_proxy.py`: synchronous file write from async context → **fixed** with `asyncio.to_thread`.

Reviewer round 2 flagged two design issues:
1. Egress proxy only recorded failures, not successes → **fixed** (success recording added with time-to-connect latency).
2. `repeat_request` blanket `except Exception` recorded all errors as target-health → **fixed** (narrowed to `OSError, TimeoutError`).

All fixes approved.

---

## Data flow diagram

```
Target host
    │
    ├── TCP connect success ──► egress_proxy writes {"is_error": false, "latency_ms": 45}
    │                           to /var/log/strix/target_health.jsonl
    │
    └── TCP connect refused ──► egress_proxy writes {"is_error": true, "error_type": "ConnectionRefusedError"}
                                to /var/log/strix/target_health.jsonl

Agent loop (host)
    │
    └── _poll_target_health() ──► docker exec cat /var/log/strix/target_health.jsonl
                                    ├── Parse each line → breaker.record(is_error=..., latency_ms=...)
                                    └── docker exec truncate -s 0 ...

repeat_request (tool, host)
    │
    ├── HTTP 200 ──► _record_target_health(is_error=False, latency_ms=elapsed_ms)
    ├── HTTP 502 ──► _record_target_health(is_error=True, latency_ms=elapsed_ms)
    └── Connection refused ──► _record_target_health(is_error=True, latency_ms=0)
```

---

## Gates cleared / remaining

| Gate | Status |
|---|---|
| S3.1 breaker target-health re-wire | ✅ Complete |
| S0 containment (PRE-3/4) | ✅ Already on main (verdict-10) |
| SGL-Core (SP1–SP8) | ✅ Already on main (verdict-09) |
| Full suite green (non-Docker) | ✅ 524 passed |
| Ruff clean on changed files | ✅ 36 pre-existing, 0 new |
| PRE-1 bl-fixture Docker tests | ⏳ Pre-existing (4 fail on main too) |

---

## Definition of Done

- [x] Breaker no longer measures agent-cycle health.
- [x] Breaker receives target-health events from egress proxy (connection outcomes).
- [x] Breaker receives target-health events from proxy tools (HTTP 5xx/429).
- [x] `_poll_target_health` consumes events from container file and clears it.
- [x] Full suite green (minus PRE-1 pre-existing Docker failures).
- [x] Ruff clean on changed files (no new errors).
- [x] Code review passed (two rounds, all issues resolved).

---

## Path forward (PM-owned gates)

1. **PM re-validation** of S3.1 on branch `sgl-s3.1 @ 678e315`.
2. **Squash-merge** `sgl-s3.1` → `main` (PM gives command after confirming).
3. **Live Gate-5 smoke** on rebuilt `strix-sandbox:prod` with S3.1 active.
4. **E1–E4** begin on the fully hardened engine. S3.1 gates unattended non-owned-target use.

---

**Session Manifest**
```
Skill: pm-auditor@2.0.0 + v2.1 · producer: CLI
Spec: strix-governance-layer (SGL-Core) · S3.1
Branch: sgl-s3.1 @ 678e315
Evidence: 524 passed/4 pre-existing failed; ruff 36 pre-existing on changed files; 2-round code review
Decision: awaiting PM validation
```
