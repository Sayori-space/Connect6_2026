"""
pixel_widgets.py – shared pixel-art primitives.

  load_pixel_font()   – load VonwaonBitmap, return family name
  pixel_font(size)    – QFont using the pixel typeface
  PixelButton         – double-border retro button (black/white only)
  StarBackground      – static star-field on pure black
"""

import os
import random
from typing import List, Tuple

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PyQt5.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.sound_manager import SoundManager

# ── Font ───────────────────────────────────────────────────────────────

_FONT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "font", "VonwaonBitmap-16px.ttf")
)
_PIXEL_FAMILY: str = ""


def load_pixel_font() -> str:
    """Register the bitmap font and return its family name."""
    global _PIXEL_FAMILY
    if _PIXEL_FAMILY:
        return _PIXEL_FAMILY
    fid = QFontDatabase.addApplicationFont(_FONT_PATH)
    if fid >= 0:
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            _PIXEL_FAMILY = families[0]
    return _PIXEL_FAMILY


def pixel_font(size: int = 12, bold: bool = False) -> QFont:
    """Return a QFont using the pixel typeface (fallback: Courier New)."""
    family = _PIXEL_FAMILY or "Courier New"
    f = QFont(family, size)
    f.setBold(bold)
    return f


# ── Double-border pixel button ─────────────────────────────────────────

class PixelButton(QPushButton):
    """
    Retro double-border button (mirrors the reference screenshots).

    Normal  : transparent bg · white double border · white text
    Hover   : white bg · black double border · black text  (animated)
    Pressed : same as hover, slightly transparent
    Disabled: dim border and text
    """

    _OUTER_R   = 10    # outer corner radius (px)
    _GAP       = 5     # gap between outer and inner border (px)
    _BW        = 1.5   # border line width
    _ANIM_STEP = 0.14  # progress per 16 ms frame ≈ 110 ms full transition

    def __init__(self, text: str = "", font_size: int = 14, parent=None,
                 silent: bool = False):
        super().__init__(text, parent)
        self.setFont(pixel_font(font_size))
        self.setAttribute(Qt.WA_Hover, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self._hovered = False
        self._hover_progress: float = 0.0   # 0.0 = normal, 1.0 = fully hovered
        self._silent = silent

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

        if not self._silent:
            self.clicked.connect(lambda: SoundManager.instance().play_click())

    # ── animation ──────────────────────────────────────────────────────

    def _tick_anim(self) -> None:
        target = 1.0 if (self._hovered and self.isEnabled()) else 0.0
        if self._hover_progress < target:
            self._hover_progress = min(target, self._hover_progress + self._ANIM_STEP)
        else:
            self._hover_progress = max(target, self._hover_progress - self._ANIM_STEP)
        self.update()
        if self._hover_progress == target:
            self._anim_timer.stop()

    # ── painting ───────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        disabled = not self.isEnabled()
        pressed  = self.isDown()

        bw = self._BW
        OR = self._OUTER_R
        G  = self._GAP
        IR = max(3, OR - 3)

        if disabled:
            # Static: solid black fill, dim borders/text
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0))
            p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            bd = QColor(60, 60, 60)
            fg = QColor(70, 70, 70)
        elif pressed:
            # Static: full white fill, black text
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            bd = QColor(0, 0, 0)
            fg = QColor(0, 0, 0)
        else:
            # Animated: fade white bg in, cross-fade borders/text white→black
            t = self._hover_progress
            bg_alpha = int(255 * t)
            if bg_alpha > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, bg_alpha))
                p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            v = int(255 * (1.0 - t))
            bd = QColor(v, v, v)
            fg = QColor(v, v, v)

        # Outer border
        p.setPen(QPen(bd, bw))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(bw / 2, bw / 2, w - bw, h - bw), OR, OR)

        # Inner border
        p.drawRoundedRect(QRectF(G, G, w - 2 * G, h - 2 * G), IR, IR)

        # Label
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.text())

    # ── hover tracking ─────────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._anim_timer.start()
        if not self._silent and self.isEnabled():
            SoundManager.instance().play_hover()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._anim_timer.start()
        super().leaveEvent(event)


# ── Star field ─────────────────────────────────────────────────────────

_Star = Tuple[float, float, int, int]   # (x_frac, y_frac, size_px, brightness)


class StarBackground(QWidget):
    """
    Static star-field widget (pure black background + tiny white dots).
    Stars are seeded deterministically so they stay consistent.
    """

    def __init__(self, count: int = 180, parent=None):
        super().__init__(parent)
        rng = random.Random(0xC6)
        self._stars: List[_Star] = []
        for _ in range(count):
            x  = rng.random()
            y  = rng.random()
            sz = rng.choices([1, 1, 2], weights=[7, 2, 1])[0]
            br = rng.randint(70, 255)
            self._stars.append((x, y, sz, br))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        w, h = self.width(), self.height()
        for sx, sy, sz, br in self._stars:
            p.fillRect(int(sx * w), int(sy * h), sz, sz, QColor(br, br, br))


# ── Replace StarBackground with the GPU shader version if available ──────
# home_screen.py / dialogs.py import StarBackground from here; swapping it
# out here means no changes needed elsewhere.

try:
    from ui.shader_background import ShaderBackground as StarBackground  # noqa: F811
except Exception as _e:
    print(f"[pixel_widgets] ShaderBackground unavailable ({_e}), using static fallback")
