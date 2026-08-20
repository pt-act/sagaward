"""IU-1 offline acceptance tests — per-turn request timeout wiring.

Covers spec upstream-upgrade AC-4/AC-5/AC-6 (offline, no Docker/API key):
  AC-6 (TP): timeout is forwarded to the model call.
  AC-4 (TN/no-regression): retry policy object is unchanged.
  AC-5 (treatment TN): reasoning-none thinking:disabled path is unchanged.
"""

from __future__ import annotations

from strix.config.models import DEFAULT_MODEL_RETRY, request_timeout_extra_args
from strix.core.inputs import make_model_settings


# ---- AC-6: timeout wiring works (true-positive) ----
def test_request_timeout_extra_args_positive() -> None:
    assert request_timeout_extra_args(5.0) == {"timeout": 5.0}
    assert request_timeout_extra_args(300) == {"timeout": 300.0}


def test_request_timeout_extra_args_zero_and_none() -> None:
    assert request_timeout_extra_args(0) is None
    assert request_timeout_extra_args(None) is None
    assert request_timeout_extra_args(-1) is None


def test_make_model_settings_forwards_timeout() -> None:
    ms = make_model_settings(None, model_name="deepseek-v4-flash", request_timeout=5)
    assert ms.extra_args == {"timeout": 5.0}


def test_make_model_settings_default_no_timeout() -> None:
    # No request_timeout -> no extra_args override (backward compatible).
    ms = make_model_settings(None, model_name="deepseek-v4-flash")
    assert ms.extra_args is None


# ---- AC-4: retry policy unchanged (true-negative / no-regression) ----
def test_retry_policy_object_unchanged_with_timeout() -> None:
    ms = make_model_settings(None, model_name="deepseek-v4-flash", request_timeout=5)
    assert ms.retry is DEFAULT_MODEL_RETRY


def test_retry_policy_object_unchanged_without_timeout() -> None:
    ms = make_model_settings(None, model_name="deepseek-v4-flash")
    assert ms.retry is DEFAULT_MODEL_RETRY


# ---- AC-5: reasoning-none thinking:disabled preserved (treatment true-negative) ----
def test_thinking_disabled_preserved_with_timeout() -> None:
    ms = make_model_settings("none", model_name="deepseek-v4-flash", request_timeout=5)
    assert ms.extra_body == {"thinking": {"type": "disabled"}}
    assert ms.extra_args == {"timeout": 5.0}  # both coexist, no clobber


def test_thinking_disabled_preserved_without_timeout() -> None:
    ms = make_model_settings("none", model_name="deepseek-v4-flash")
    assert ms.extra_body == {"thinking": {"type": "disabled"}}
