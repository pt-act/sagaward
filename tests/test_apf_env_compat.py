"""The public ``SAGAWARD_*`` prefix and the one-time ``STRIX_*`` compatibility shim.

The full pydantic settings load is exercised by the application environment and the
integration replay; this file pins the shim and the declared aliases in the fence's
minimal test environment.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest

from sagaward import _env_compat


def test_legacy_env_is_copied_to_the_public_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """A legacy STRIX_* value reaches the public prefix, with one warning."""
    monkeypatch.delenv("SAGAWARD_LLM", raising=False)
    monkeypatch.setenv("STRIX_LLM", "legacy/model")
    monkeypatch.setattr(_env_compat, "_WARNED", False)

    with pytest.warns(UserWarning):
        _env_compat.apply_legacy_env()

    assert os.environ["SAGAWARD_LLM"] == "legacy/model"


def test_explicit_public_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicitly-set SAGAWARD_* value is never overwritten by its legacy twin."""
    monkeypatch.setenv("STRIX_LLM", "legacy/model")
    monkeypatch.setenv("SAGAWARD_LLM", "public/model")
    monkeypatch.setattr(_env_compat, "_WARNED", False)

    with pytest.warns(UserWarning):
        _env_compat.apply_legacy_env()

    assert os.environ["SAGAWARD_LLM"] == "public/model"


def test_the_warning_is_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shim warns on the first legacy read and stays quiet afterwards."""
    monkeypatch.delenv("SAGAWARD_LLM", raising=False)
    monkeypatch.setenv("STRIX_LLM", "legacy/model")
    monkeypatch.setattr(_env_compat, "_WARNED", False)

    with pytest.warns(UserWarning):
        _env_compat.apply_legacy_env()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _env_compat.apply_legacy_env()

    assert not [item for item in caught if issubclass(item.category, UserWarning)]


def test_settings_declare_the_public_prefix() -> None:
    """The settings aliases and the default image point at Sagaward, not upstream."""
    source = (Path(__file__).resolve().parents[1] / "sagaward/config/settings.py").read_text(
        encoding="utf-8"
    )

    assert 'alias="SAGAWARD_LLM"' in source
    assert 'alias="SAGAWARD_IMAGE"' in source
    assert 'alias="SAGAWARD_TELEMETRY"' in source
    assert "ghcr.io/pt-act/sagaward-sandbox" in source
