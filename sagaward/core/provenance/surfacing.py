"""Hash engagement content at the tool-return boundary.

The index needs the bytes *the model was shown*. Hashing at the tool return is
the one place our code sees exactly that string, unmodified by rendering, and
it keeps the surfacing half separate from the decision path.

Taint-only, like every branch that touches the index: a return value can add an
engagement digest, never a clean one.

Scope note (recorded, not implied): this covers bodies surfaced **through the
proxy tool layer**. A `curl -o file` whose body never enters a tool return is
captured only if the file's digest later matches something that did — the
Caido-side capture sweep is a named follow-up, not a claim made here.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from sagaward.core.provenance.write_hook import ledger_from_ctx


logger = logging.getLogger(__name__)

# Proxy tools whose return value carries target response content.
SURFACING_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_requests",
        "view_request",
        "repeat_request",
        "list_sitemap",
        "view_sitemap_entry",
        "scope_rules",
    },
)

_WRAPPED: set[int] = set()

MIN_LEAF_LENGTH = 8


def _string_leaves(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        if len(value) >= MIN_LEAF_LENGTH:
            out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _string_leaves(item, out)
    elif isinstance(value, list):
        for item in value:
            _string_leaves(item, out)


def surface_texts(result: str) -> tuple[str, ...]:
    """Every byte-string a proxy tool exposed: the return itself and its JSON leaves.

    Proxy tools return a JSON presentation document. Hashing only that document
    indexes the envelope, not the response body inside it, and a downloaded file
    can never match. Leaves are indexed as well, so the body matches when it is a
    field. A body rendered into prose with per-line decoration still will not
    match — that limit is recorded, not hidden.
    """
    texts: list[str] = [result]
    stripped = result.lstrip()
    if stripped.startswith(("{", "[")):
        with contextlib.suppress(TypeError, ValueError):
            _string_leaves(json.loads(result), texts)
    return tuple(dict.fromkeys(texts))


def wrap_surfacing_tool(tool: Any) -> Any:
    """Record the digest of a proxy tool's returned text into the content index."""
    if id(tool) in _WRAPPED or getattr(tool, "name", None) not in SURFACING_TOOL_NAMES:
        return tool
    invoke_tool = tool.on_invoke_tool

    async def invoke(ctx: Any, raw_input: str) -> Any:
        result = await invoke_tool(ctx, raw_input)
        ledger = ledger_from_ctx(ctx)
        if ledger is None:
            return result
        if isinstance(result, str) and result:
            for text in surface_texts(result):
                ledger.record_surfaced_content(text)
        return result

    tool.on_invoke_tool = invoke
    _WRAPPED.add(id(tool))
    return tool


def wrap_surfacing_tools(tools: list[Any]) -> list[Any]:
    """Apply the surfacing wrapper to every proxy tool in a tool list."""
    return [wrap_surfacing_tool(tool) for tool in tools]
