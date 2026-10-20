"""The AI Guruji mark (S25): a meditating Buddha, drawn as a small inline SVG so it needs no image file."""

BUDDHA_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}" role="img" '
    'aria-label="Meditating Buddha" style="flex:none;">'
    '<defs><linearGradient id="ag-robe" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#F59E0B"/><stop offset="1" stop-color="#C2410C"/></linearGradient></defs>'
    '<circle cx="32" cy="20" r="15" fill="#FEF3C7"/>'
    '<circle cx="32" cy="9.5" r="2.6" fill="#92400E"/>'
    '<circle cx="32" cy="17" r="7.2" fill="#FBBF24"/>'
    '<path d="M28.6 17.5 q1.2 0.9 2.4 0 M33 17.5 q1.2 0.9 2.4 0" stroke="#92400E" stroke-width="0.9" fill="none" stroke-linecap="round"/>'
    '<path d="M25 25.5 C20 27 18 33 18.5 40 L45.5 40 C46 33 44 27 39 25.5 C36.5 27.4 27.5 27.4 25 25.5 Z" fill="url(#ag-robe)"/>'
    '<ellipse cx="32" cy="46" rx="21" ry="7.5" fill="url(#ag-robe)"/>'
    '<ellipse cx="32" cy="41.5" rx="6" ry="2.6" fill="#FBBF24"/>'
    '<path d="M12 54 H52" stroke="#D97706" stroke-width="2" stroke-linecap="round"/>'
    "</svg>"
)


def buddha_svg(size: int = 34) -> str:
    return BUDDHA_SVG.replace("{size}", str(int(size)))
