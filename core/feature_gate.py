"""Freemium feature limits and Pro checks."""

from __future__ import annotations

from core.licensing import is_pro

FREE_RECORD_LIMIT = 100


def can_fetch_prices() -> bool:
    return is_pro()


def can_check_wishlist_availability() -> bool:
    return is_pro()


def can_use_manual_order() -> bool:
    return is_pro()


def can_play_audio_preview() -> bool:
    return is_pro()


def can_use_abc_dividers() -> bool:
    return is_pro()


def apply_record_limit(rows: list) -> tuple[list, bool]:
    """Return (possibly truncated rows, was_truncated)."""
    if is_pro() or len(rows) <= FREE_RECORD_LIMIT:
        return rows, False
    return rows[:FREE_RECORD_LIMIT], True


def upgrade_message(feature: str) -> str:
    return f"{feature} is a Pro feature. Upgrade to unlock unlimited collection tools."
