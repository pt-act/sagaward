"""IU-3 offline acceptance tests — positive reasoning_effort for thinking-only providers.

Covers spec iu3-reasoning-effort AC-1..AC-5 (offline, no Docker/API key).

Design: a positive reasoning_effort is emitted via the SDK-native
``ModelSettings.reasoning = Reasoning(effort=...)`` path (the agents SDK forwards
it as the top-level ``reasoning_effort`` create-arg to the OpenAI-compatible
client). For litellm-known reasoners this is the long-standing path. Thinking-only
providers that litellm does not recognise (Ox Alpha / x-preview-f-free) opt in via
``STRIX_FORCE_REASONING_EFFORT`` (force_reasoning_effort=True) -- OFF by default so
models that previously emitted no reasoning arg (e.g. z-ai/glm-5) are byte-identical
(no silent treatment change). ``max``/``xhigh`` clamp to ``high``. The ``none`` ->
``extra_body.thinking:disabled`` path is unchanged.
"""

from __future__ import annotations

import json
import typing

import httpx
import pytest
from agents.model_settings import ModelSettings
from agents.models.interface import ModelTracing
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from strix.config.settings import LlmSettings, ReasoningEffort
from strix.core.inputs import make_model_settings


THINKING_ONLY = "x-preview-f-free"      # litellm does NOT know this as a reasoner
KNOWN_REASONER = "deepseek-v4-flash"    # litellm-known reasoner
NON_REASONER = "z-ai/glm-5"             # a3ce170 M0 baseline model; not litellm-known


# ---- AC-1: thinking-only provider opts in via force flag (true-positive) ----
def test_force_flag_sets_reasoning_for_thinking_only() -> None:
    ms = make_model_settings("low", model_name=THINKING_ONLY, force_reasoning_effort=True)
    assert ms.reasoning is not None
    assert ms.reasoning.effort == "low"
    assert ms.extra_body is None  # never thinking:disabled for positive effort


def test_force_flag_high() -> None:
    ms = make_model_settings("high", model_name=THINKING_ONLY, force_reasoning_effort=True)
    assert ms.reasoning is not None and ms.reasoning.effort == "high"


# ---- Preservation: flag OFF reproduces a3ce170 (no silent treatment change) ----
def test_flag_off_preserves_a3ce170_non_reasoner() -> None:
    # glm-5 (a3ce170 baseline) + high, flag OFF -> NO reasoning emitted (as before).
    ms = make_model_settings("high", model_name=NON_REASONER)
    assert ms.reasoning is None
    ms2 = make_model_settings("high", model_name=THINKING_ONLY)
    assert ms2.reasoning is None


# ---- AC-5 + clamp: max/xhigh accepted by enum, clamped to SDK-valid "high" ----
def test_max_and_xhigh_clamp_to_high() -> None:
    for lvl in ("max", "xhigh"):
        ms = make_model_settings(lvl, model_name=THINKING_ONLY, force_reasoning_effort=True)
        assert ms.reasoning is not None and ms.reasoning.effort == "high"


def test_enum_includes_max() -> None:
    assert "max" in typing.get_args(ReasoningEffort)


# ---- AC-2: none / thinking:disabled path byte-unchanged (preservation TN) ----
def test_none_path_unchanged() -> None:
    ms = make_model_settings("none", model_name=THINKING_ONLY, force_reasoning_effort=True)
    assert ms.extra_body == {"thinking": {"type": "disabled"}}
    assert ms.reasoning is None  # none path never emits reasoning, even with force flag


# ---- AC-3: IU-1 timeout preserved alongside reasoning (no-clobber) ----
def test_timeout_and_effort_coexist() -> None:
    ms = make_model_settings(
        "low", model_name=THINKING_ONLY, request_timeout=300, force_reasoning_effort=True
    )
    assert (ms.extra_args or {}).get("timeout") == 300.0
    assert ms.reasoning is not None and ms.reasoning.effort == "low"


# ---- AC-4: litellm-known reasoner path unchanged (native reasoning, no flag needed) ----
def test_known_reasoner_uses_reasoning_without_flag() -> None:
    ms = make_model_settings("low", model_name=KNOWN_REASONER)
    assert ms.reasoning is not None and ms.reasoning.effort == "low"


# ─── v0.2.0 round-2 additions (validator round-1 reconciliation) ──────────────

def test_settings_load_max(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-5 end-to-end: a Settings load with STRIX_REASONING_EFFORT=max validates."""
    monkeypatch.setenv("STRIX_REASONING_EFFORT", "max")
    settings = LlmSettings(_env_file=None)
    assert settings.reasoning_effort == "max"


def _wire_client(captured: dict[str, object]) -> AsyncOpenAI:
    """An OpenAI AsyncClient whose transport records the request body and returns a
    minimal valid chat completion (offline wire capture — no network)."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-wire-test",
                "object": "chat.completion",
                "created": 0,
                "model": THINKING_ONLY,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    return AsyncOpenAI(
        base_url="http://wire-test.local/v1",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_wire_reasoning_effort_on_the_wire() -> None:
    """AC-1/AC-6a (v0.2.0): through the REAL agents-SDK chat-completions path, the
    force-flag model settings put reasoning_effort into the outgoing request body."""
    captured: dict[str, object] = {}
    model = OpenAIChatCompletionsModel(
        model=THINKING_ONLY, openai_client=_wire_client(captured)
    )
    ms = make_model_settings("low", model_name=THINKING_ONLY, force_reasoning_effort=True)
    await model.get_response(
        system_instructions="s",
        input="hi",
        model_settings=ms,
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=ModelTracing.DISABLED,
    )
    body = captured["body"]  # type: ignore[index]
    assert body["reasoning_effort"] == "low"
    assert "allowed_openai_params" not in body


@pytest.mark.asyncio
async def test_superseded_v010_extra_args_form_is_rejected_by_sdk() -> None:
    """Reconciliation guard: the superseded v0.1.0 interface (reasoning_effort inside
    extra_args) trips the SDK's duplicate-key TypeError on the chat-completions path.
    Documents mechanically why the SDK-native Reasoning form is the contract."""
    captured: dict[str, object] = {}
    model = OpenAIChatCompletionsModel(
        model=THINKING_ONLY, openai_client=_wire_client(captured)
    )
    superseded = ModelSettings(
        extra_args={
            "reasoning_effort": "low",
            "allowed_openai_params": ["reasoning_effort"],
        }
    )
    with pytest.raises(TypeError, match="multiple values for keyword argument"):
        await model.get_response(
            system_instructions="s",
            input="hi",
            model_settings=superseded,
            tools=[],
            output_schema=None,
            handoffs=[],
            tracing=ModelTracing.DISABLED,
        )
