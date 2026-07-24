# Phase 3 Close-Out — Coder Instructions

**Branch:** `phase-3-rebased` · **Status:** 8 TGs implemented, gate green, but two items block "complete" + one hygiene item.
**Do these three, in order. Keep the gate green (`pytest`, `ruff`, `ruff format --check`, `mypy --strict` on changed, `pyright` on inventory, `bandit -c pyproject.toml`).**

---

## Task 1 — HIGH: wire the inventory tool surface into the agent (F-10)

**Problem.** The 9 inventory `@function_tool`s in `strix/tools/inventory/tools.py` are never added to `_BASE_TOOLS` in `strix/agents/factory.py`, so the agent cannot call them. The E2E test imports the functions directly (mocks the agents SDK), so the green suite does not catch this. F-10 ("the agent *can* build the map, classify a param, request its class-spray") is unmet end-to-end.

**Decision (PM): wire the Phase-2 OOB tools in the same change.** They (`mint_oob_token`, `poll_oob_callbacks`, `confirm_oob_callback`, `report_oob_confirmed_candidate`) are in the same unwired state, and they are the **deterministic disposer the whole engine depends on** — without them the agent can propose an SSRF/XXE candidate but has no tool to *confirm* it via callback at runtime. That is a more fundamental gap than the inventory one. Same file, same one-line-per-tool pattern, near-zero marginal cost. Add them to `_BASE_TOOLS` alongside the inventory tools. (They are already scope-bounded with a live-oracle gate from Phase 2, so exposing them does not auto-contact OAST outside scope — safe to wire.)

### 1a. Add the import block to `strix/agents/factory.py` (with the existing tool imports, ~line 18–54)

```python
from strix.tools.inventory.tools import (
    build_ranked_surface_map,
    classify_inventory_params,
    collect_inventory_from_code,
    collect_inventory_from_proxy,
    enrich_inventory_from_forms,
    enrich_inventory_from_js,
    enrich_inventory_from_openapi,
    load_ranked_surface_map,
    spray_inventory_params,
)
```

### 1b. Add the 8 black-box-safe tools to `_BASE_TOOLS` (the tuple at ~line 322)

Append before the closing `)`:

```python
    # Phase 3 — attack-surface inventory (black-box safe)
    collect_inventory_from_proxy,
    build_ranked_surface_map,
    load_ranked_surface_map,
    classify_inventory_params,
    spray_inventory_params,
    enrich_inventory_from_openapi,
    enrich_inventory_from_js,
    enrich_inventory_from_forms,
```

### 1c. Gate the white-box-only tool on `is_whitebox` (the `if is_root:` block at ~line 378)

`collect_inventory_from_code` (and the reachability annotation it drives) must be exposed **only in white-box mode** — the spec requires black-box runs to omit the code collector + reachability cleanly (F-10, TG7.5). Replace:

```python
    if is_root:
        tools: list[Tool] = [*_BASE_TOOLS, finish_scan]
    else:
        tools = [*_BASE_TOOLS, agent_finish]
```

with:

```python
    tools: list[Tool] = [*_BASE_TOOLS, finish_scan if is_root else agent_finish]
    if is_whitebox:
        tools.append(collect_inventory_from_code)
```

> **Decision (PM): the embedded reachability form is acceptable — no separate query tool needed.** Reachability is annotated onto endpoints during `collect_inventory_from_code` and surfaces through the ranked map (`build_ranked_surface_map` / `load_ranked_surface_map`), so the agent can already read it. A standalone "query reachability for endpoint X" tool is a nice-to-have, not an F-10 requirement, since the data is exposed via the map. Defer it; revisit only if the agent later needs on-demand reachability without rebuilding the map.

### 1d. Add a registry-presence test — this is the test that would have caught the gap

New file `tests/test_inventory_tool_registration.py`:

```python
"""F-10: inventory tools must be reachable through the built agent, not just importable."""

from __future__ import annotations

import unittest

from strix.agents.factory import build_strix_agent


def _tool_names(agent: object) -> set[str]:
    return {t.name for t in agent.tools}  # type: ignore[attr-defined]


class TestInventoryToolRegistration(unittest.TestCase):
    BLACKBOX_TOOLS = {
        "collect_inventory_from_proxy",
        "build_ranked_surface_map",
        "load_ranked_surface_map",
        "classify_inventory_params",
        "spray_inventory_params",
        "enrich_inventory_from_openapi",
        "enrich_inventory_from_js",
        "enrich_inventory_from_forms",
    }

    def test_blackbox_agent_exposes_inventory_tools(self) -> None:
        agent = build_strix_agent(is_root=True, is_whitebox=False)
        self.assertTrue(self.BLACKBOX_TOOLS.issubset(_tool_names(agent)))

    def test_blackbox_agent_omits_code_collector(self) -> None:
        agent = build_strix_agent(is_root=True, is_whitebox=False)
        self.assertNotIn("collect_inventory_from_code", _tool_names(agent))

    def test_whitebox_agent_adds_code_collector(self) -> None:
        agent = build_strix_agent(is_root=True, is_whitebox=True)
        self.assertIn("collect_inventory_from_code", _tool_names(agent))
```

> If `build_strix_agent` cannot run offline (SDK/sandbox deps), mirror the mock pattern already used at the top of `tests/test_inventory_tools.py` so the test stays hermetic. The assertion (tool names present/absent in the built agent's `.tools`) is the point — keep it.

---

## Task 2 — MEDIUM: add the 6th PBT invariant (reachability soundness, 7.6)

**Problem.** Gate 3 / task 8.5 require six PBT invariants; only 5 exist as `@given` tests. Reachability soundness (7.6) is covered only by Tier-1 examples. The property *does* hold by construction (`strix/core/inventory/parsers/reachability.py:106` — `status = "reachable" if sinks else "unreachable"`), but the stated deliverable is unmet.

**Fix.** Add a property test to `tests/test_inventory_parser_reachability.py` asserting the invariant `∀ flagged sink k: (∃ path) ∨ marked_unreachable(k)` — i.e. a `reachable` result always carries a non-empty path, and every result's status is one of the three legal values:

```python
import hypothesis.strategies as st
from hypothesis import given

# strategy over synthetic handler bodies that may or may not contain sinks
_SINK_SNIPPETS = ["cursor.execute(q)", "os.system(cmd)", "open(p)", "requests.get(u)"]
_SAFE_SNIPPETS = ["return 1", "x = a + b", "logger.info(msg)"]


class TestReachabilitySoundnessPBT(unittest.TestCase):
    @given(
        st.lists(st.sampled_from(_SINK_SNIPPETS + _SAFE_SNIPPETS), max_size=6),
    )
    def test_reachable_always_carries_a_path(self, lines: list[str]) -> None:
        body = "\n".join(lines)
        result = analyze_handler(body)  # use the real entry point in reachability.py
        self.assertIn(result.status, {"reachable", "unreachable", "unknown"})
        if result.status == "reachable":
            # soundness: a flagged-reachable sink must carry a concrete path
            self.assertTrue(result.sinks, "reachable status with empty path violates 7.6")
```

> Use the actual public function name from `reachability.py` (the one the Tier-1 tests call — looked like `analyze_handler`/`analyze`; match it).

**Decision (PM): write the real PBT — do not waive.** This is a bounty-grade engine whose flagship differentiator is PBT-validated soundness; waiving 1 of the 6 named security invariants in that rigor story is the wrong precedent. More concretely, the structural guarantee at line 106 *can drift* — a future refactor could set `status="reachable"` on a path that no longer populates `sinks`, and only a property test catches that regression. The PBT is ~10 lines and exists precisely to regression-proof the invariant against future edits. Waiver is justified only when a property is untestable or prohibitively expensive; neither applies here.

---

## Task 3 — LOW (hygiene): the leaked addendum, and test `/tmp` paths

### 3a. The leaked research addendum — what actually happened (the operator was confused, here's why)

- `propose-dispose-addendum.md` was committed **at the repo root** inside the TG8 commit `401becd`, then deleted in `4057a67`.
- **At HEAD it is gone from the tracked tree** — that's why `git ls-files` / browsing the branch shows nothing. Moving copies into `.agents/` (gitignored, `.gitignore:88`) also keeps those copies untracked. Both observations are correct.
- **But the original blob still lives in branch history** at commit `401becd`. Confirmed: `git show 401becd:propose-dispose-addendum.md` returns the full content. So "I don't see it" is true for the working tree, **false for history**.
- This means the working tree wasn't clean when TG8 was committed (a stray file got swept in — avoid `git add -A`/`git add .`; stage explicit paths).

**Remediation — pick one before Phase 3 merges to main:**
- **Easiest: squash-merge** `phase-3-rebased` → main. A squash produces a single commit with the HEAD tree (no addendum), so the blob never enters main. No history surgery.
- **If you keep a regular merge:** rewrite history to drop the file from `401becd` first — interactive rebase (`git rebase -i 7223815`, mark `401becd` as `edit`, `git rm --cached propose-dispose-addendum.md`, `git commit --amend`, `git rebase --continue`), or `git filter-repo --path propose-dispose-addendum.md --invert-paths`. Force-push the rebased branch.
- Do **not** just rely on the existing delete commit — the add+delete pair both ride into main on a normal merge.

### 3b. Hardcoded `/tmp` paths in tests (non-hermetic; caused the 3 sandbox failures)

`test_inventory_scoring.py` (`/tmp/strix_test_scoring`), `test_inventory_collectors.py` (`/tmp/strix_inventory_fastapi_fixture.py`), and pre-existing `test_core_paths.py` (`/tmp/strix_repos`) write to literal absolute paths. Switch them to `tempfile.TemporaryDirectory` / pytest `tmp_path` — the pattern is already done correctly in `tests/test_inventory_tools.py`, so copy it. Low priority, but fix before Phase 4 multiplies it.

---

## Acceptance for "Phase 3 complete"
- [ ] Task 1: 8 inventory tools **+ the 4 OOB tools** in `_BASE_TOOLS`; `collect_inventory_from_code` white-box-gated; `tests/test_inventory_tool_registration.py` green.
- [ ] Task 2: 7.6 `@given` reachability-soundness PBT added (no waiver).
- [ ] Task 3a: leaked addendum scrubbed from the history that will reach main — **squash-merge** `phase-3-rebased` → main (PM-preferred: zero history surgery).
- [ ] Task 3b: `/tmp` test paths moved to tempfile.
- [ ] Full gate green; PROGRESS.md / current_focus.md updated to reflect F-10 wiring (inventory + OOB) and the 7.6 PBT.

> Correction for the next summary: TG8 ships **9** `@function_tool`s, not 7; and the bandit line should read `bandit -r strix/ -c pyproject.toml` (the bare form exits non-zero on pre-existing low findings).
