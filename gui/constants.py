"""Shared GUI typography and settings labels."""

from __future__ import annotations

FONT_SEGOE_UI = "Segoe UI"
FONT_SEGOE_UI_SEMIBOLD = "Segoe UI Semibold"
FONT_XS = 12
FONT_SM = 14
FONT_MD = 15
FONT_LG = 16
FONT_XL = 20
FONT_2XL = 26

DIVIDER_MODE_LABELS = {
  "none": "Off",
  "letter": "By letter (A–Z)",
  "abc": "By shelf (A/B/C)",
}
DIVIDER_MODE_BY_LABEL = {v: k for k, v in DIVIDER_MODE_LABELS.items()}

POLL_SECONDS_DEFAULT = 300
