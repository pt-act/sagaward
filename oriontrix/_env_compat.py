"""One-time compatibility for legacy ``STRIX_*`` environment variables.

The public prefix is ``ORIONTRIX_*``. A process that still exports the legacy
``STRIX_*`` names gets those values copied to the new names before settings
load, with a single warning per process. An explicitly-set ``ORIONTRIX_*``
value wins over its legacy counterpart.
"""

from __future__ import annotations

import os
import warnings


_WARNED = False


def apply_legacy_env() -> None:
    """Copy legacy ``STRIX_*`` values to ``ORIONTRIX_*`` once, with a warning."""
    global _WARNED  # noqa: PLW0603

    legacy = sorted(key for key in os.environ if key.startswith("STRIX_"))
    if not legacy:
        return
    for key in legacy:
        new_key = "ORIONTRIX_" + key[len("STRIX_") :]
        if new_key not in os.environ:
            os.environ[new_key] = os.environ[key]
    if not _WARNED:
        warnings.warn(
            f"legacy STRIX_* environment variables detected ({len(legacy)}); "
            "they are read once for compatibility — use ORIONTRIX_* instead",
            UserWarning,
            stacklevel=2,
        )
        _WARNED = True
