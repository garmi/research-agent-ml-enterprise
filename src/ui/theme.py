"""Single source of truth for UI theme, palette, typography, and spacing (Slice S1 Round 3).

Palette: Calm navy/slate with one blue accent.
All colors, font sizes, and spacing sets are defined here once as constants.
"""

from __future__ import annotations

# Palette: Calm Navy / Slate with Cobalt Blue accent
COLOR_PRIMARY = "#2563EB"
COLOR_PRIMARY_HOVER = "#1D4ED8"
COLOR_BG_MAIN = "#FFFFFF"
COLOR_BG_SURFACE = "#F8FAFC"
COLOR_BG_CARD = "#FFFFFF"

# Neutral borders & text
COLOR_BORDER = "#E2E8F0"
COLOR_BORDER_STRONG = "#CBD5E1"
COLOR_TEXT_PRIMARY = "#0F172A"
COLOR_TEXT_SECONDARY = "#475569"
COLOR_TEXT_MUTED = "#64748B"

# Neutral Info & Disabled Boxes
COLOR_INFO_BOX_BG = "#F1F5F9"
COLOR_INFO_BOX_TEXT = "#334155"
COLOR_INFO_BOX_BORDER = "#CBD5E1"

COLOR_DISABLED_BOX_BG = "#F1F5F9"
COLOR_DISABLED_BOX_TEXT = "#475569"
COLOR_DISABLED_BOX_BORDER = "#CBD5E1"

COLOR_DISABLED_BTN_BG = "#E2E8F0"
COLOR_DISABLED_BTN_TEXT = "#64748B"

# Status Badges
COLOR_STATUS_PUBLISH_READY_TEXT = "#065F46"
COLOR_STATUS_PUBLISH_READY_BG = "#ECFDF5"
COLOR_STATUS_PUBLISH_READY_BORDER = "#A7F3D0"

COLOR_STATUS_REVISE_TEXT = "#92400E"
COLOR_STATUS_REVISE_BG = "#FFFBEB"
COLOR_STATUS_REVISE_BORDER = "#FDE68A"

COLOR_STATUS_BLOCKED_TEXT = "#991B1B"
COLOR_STATUS_BLOCKED_BG = "#FEF2F2"
COLOR_STATUS_BLOCKED_BORDER = "#FECACA"

COLOR_STATUS_NOT_PUBLISHABLE_TEXT = "#334155"
COLOR_STATUS_NOT_PUBLISHABLE_BG = "#F1F5F9"
COLOR_STATUS_NOT_PUBLISHABLE_BORDER = "#CBD5E1"

# Typography Scale
FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
FONT_SIZE_XS = "0.75rem"    # 12px
FONT_SIZE_SM = "0.85rem"    # 13.6px
FONT_SIZE_BASE = "0.95rem"  # 15.2px
FONT_SIZE_LG = "1.1rem"     # 17.6px
FONT_SIZE_XL = "1.35rem"    # 21.6px

# Spacing Scale
SPACING_XS = "0.25rem"   # 4px
SPACING_SM = "0.5rem"    # 8px
SPACING_MD = "0.85rem"   # 13.6px
SPACING_LG = "1.25rem"   # 20px
SPACING_XL = "1.75rem"   # 28px
