# Verdict — S3.1 Breaker target-request health — round 6

## Header
```
spec_id:    strix-governance-layer (S3.1)
validator:  opus-4.8-pm-auditor (distinct from producer mimo/mimo-v2.5-pro)
reviewed:   branch sgl-s3.1 @ 678e315 (off squash-merged main incl. deploy-fix) + validator-run suite
companion:  pm-decision-breaker-target-health.md (the S3.1 requirement)
timestamp:  2026-06-21 10:00 UTC
```

## Decision
```
status: approved — pending one 10-second live containment re-confirm before merge
```

S3.1 correctly re-sources the breaker from target-request health, preserves the containment proved
in verdict-10 (additive only), and the full suite is green on my own run. One quick live check is
required because this touched the enforcer file (`egress_proxy.py`) — verify, don't assume.

## Independent verification

**Breaker re-sourced (the S3.1 requirement):**
- Agent-cycle `breaker.record()` **removed** from `_run_cycle`; `breaker.record` now lives only in
  `_poll_target_health` (`execution.py:511`) and `_record_target_health` (`tools/proxy/tools.py`).
- Two correct target-health sources, matching `pm-decision-breaker-target-health.md`:
  (a) **egress proxy** writes per-connection events (latency + connection refused/timeout/reset) to
  `/var/log/strix/target_health.jsonl`; the host loop polls them via `docker_client.exec_read_file`
  and feeds the breaker. (b) **`repeat_request`** records **HTTP 5xx/429** and connection errors.
- This is target health, not agent-cycle wall time. The defect S3.1 existed to fix is closed.

**Containment preserved (verdict-10 not regressed):**
- `egress_proxy.py` diff is **additive only** — health-recording calls wrap the existing
  decide→forward/deny path; no decision/reset logic removed.
- SP2 fail-closed `decide()` gate in `repeat_request` **intact** (`tools.py:429-448`).
- The "narrowed except" actually **adds** an `except (OSError, TimeoutError)` ahead of the
  **retained** blanket `except Exception` — no exception path left uncaught, no crash route.

**Robustness:** `_poll_target_health` returns silently on every failure (no breaker / no container /
exec error / JSON error) and `breaker.record` is wrapped best-effort — a poll failure cannot crash
the agent loop or affect enforcement.

**Gate-neutral:** health recording is a side-effect; replays/dispositions are unchanged.

**Suite:** validator-run `uv run pytest tests/ -q` → **524 passed, 4 skipped, 19 subtests** (Docker
absent → bl-fixture skips). Consistent with prior runs.

## Required before merge (10s, no LLM) — confirm the enforcer still enforces
Because `egress_proxy.py` changed, rebuild and re-run the deterministic containment test from
verdict-10. The make-or-break stays the **pentester → BLOCKED** line:
```bash
docker build -f containers/Dockerfile.prod --target prod -t strix-sandbox:prod .
docker rm -f ct 2>/dev/null
docker run -d --user root --name ct --cap-add NET_ADMIN --cap-add NET_RAW \
  -e STRIX_EGRESS_ENFORCE=1 -e STRIX_SCOPE_RULES="" strix-sandbox:prod tail -f /dev/null
sleep 6
docker exec -u pentester ct sh -c 'curl -s --max-time 5 http://example.com >/dev/null && echo BYPASS || echo BLOCKED'
docker logs ct 2>&1 | grep -i ModuleNotFound || echo "proxy-clean"
docker rm -f ct
```
Expect `BLOCKED` + `proxy-clean`. If so, merge is cleared.

## Minor (non-blocking)
- **No direct test** of the new feed path (poller → breaker; `repeat_request` 5xx/429 → breaker).
  The breaker *unit* tests still pass (the module is unchanged), but the S3.1 *wiring* is untested.
  Recommend a focused test: a synthetic `target_health.jsonl` with >25% error events drives the
  breaker OPEN via `_poll_target_health`; a 503 replay drives `_record_target_health`. Add in a
  follow-up; not blocking.
- `docker_client` `exec_run` tuple-unpack fix + new `exec_command/exec_read_file`: claimed; suite
  green; host-side only (no containment surface).

## Status of S3.1 vs the program
S3.1 was the deferred "required before unattended non-owned-target use" item — not a gate on E1–E4.
Approving it does not change E1–E4 readiness (still gated on the live M0 run), but it closes the
last known containment-quality gap: the breaker now actually detects target degradation.

## Session Manifest
```
Skill: pm-auditor@2.0.0 + v2.1 · validator: opus-4.8-pm-auditor
Spec: strix-governance-layer S3.1 · Round 6 · Branch sgl-s3.1 @ 678e315
Evidence: validator-run full suite 524/4-skip; egress_proxy additive-only diff; SP2 gate intact;
          _poll_target_health best-effort; breaker.record removed from cycle path
Decision: approved pending 10s live containment re-confirm (pentester BLOCKED on rebuilt image)
Prior conflict: none · Self-check: passed · Drift: none
```
