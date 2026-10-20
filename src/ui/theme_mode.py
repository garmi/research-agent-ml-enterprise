"""Light / dark page theme (S18, S19b).

The page's design system is light: CSS variables plus many inline colours in card HTML, and data grids
drawn on a canvas. Recolouring each of those by selector kept missing some (white cards under light
text), so dark mode is one page-wide rule instead: the rendered page is inverted with its hues turned
back (hue-rotate 180deg), which keeps blues blue and greens green while light backgrounds become dark
and dark text becomes light. Images and video are inverted a second time so they keep their colours.
"""

from __future__ import annotations

from typing import Any, Mapping

THEMES = ("light", "dark")

_DARK = """
<style>
html { background: #FFFFFF; filter: invert(0.92) hue-rotate(180deg); }
img, video, picture, canvas.media, [data-testid="stImage"] img { filter: invert(1) hue-rotate(180deg); }
</style>
"""


def theme_from_query(params: Mapping[str, Any]) -> str:
    """The theme named in the URL (?theme=dark), else light."""
    value = str((params or {}).get("theme") or "").lower()
    return value if value in THEMES else "light"


def theme_css(theme: str) -> str:
    """The stylesheet to add for a theme; light is the page's own design, so it adds nothing."""
    return _DARK if theme == "dark" else ""
