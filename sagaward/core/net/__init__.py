"""Pure, importable network trust primitives for sagaward outbound validation."""

from __future__ import annotations

from sagaward.core.net.classifier import classify_ip_address, is_internal_target
from sagaward.core.net.corpus import EXTERNAL_PUBLIC_CORPUS, INTERNAL_CORPUS, METADATA_CORPUS
from sagaward.core.net.ip_decoder import decode_ip_address
from sagaward.core.net.normalize import normalize_url
from sagaward.core.net.oob import (
    NullOOBConfirmationStrategy,
    OOBConfirmationStrategy,
    confirm_oob,
    get_oob_confirmation_strategy,
    set_oob_confirmation_strategy,
)
from sagaward.core.net.redirect import (
    RedirectInternalTargetError,
    RedirectLoopError,
    RedirectValidationError,
    validate_redirect_chain,
)


__all__ = [
    "EXTERNAL_PUBLIC_CORPUS",
    "INTERNAL_CORPUS",
    "METADATA_CORPUS",
    "NullOOBConfirmationStrategy",
    "OOBConfirmationStrategy",
    "RedirectInternalTargetError",
    "RedirectLoopError",
    "RedirectValidationError",
    "classify_ip_address",
    "confirm_oob",
    "decode_ip_address",
    "get_oob_confirmation_strategy",
    "is_internal_target",
    "normalize_url",
    "set_oob_confirmation_strategy",
    "validate_redirect_chain",
]
