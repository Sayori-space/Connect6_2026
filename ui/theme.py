"""
Pixel mono theme – black/white only.
All button styling is handled by PixelButton; this file only
defines colour constants used across board and info widgets.
"""

# ── Global palette ──────────────────────────────────────────────────────
BG         = "#000000"   # pure black – app background
FG         = "#FFFFFF"   # pure white – text / borders
DIM        = "#888888"   # secondary / dim text

# ── Board ───────────────────────────────────────────────────────────────
BOARD_BG   = "#2A2A2A"   # dark-gray playing area
BOARD_LINE = "#FFFFFF"   # grid lines
STAR_POINT = "#606060"   # subtle star-point dots

# ── Stones ──────────────────────────────────────────────────────────────
BLACK_STONE_TOP       = "#303030"
BLACK_STONE_HIGHLIGHT = "#787878"   # brighter so stone reads on dark board

WHITE_STONE_TOP       = "#F2F2F2"
WHITE_STONE_HIGHLIGHT = "#FFFFFF"
WHITE_STONE_SHADOW    = "#C0C0C0"

# ── Win highlight ───────────────────────────────────────────────────────
WIN_GLOW   = "#FFE040"   # golden yellow – visible on both stone colours
