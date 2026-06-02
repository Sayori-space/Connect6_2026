"""
pixel_widgets.py：共享像素风基础控件。

  load_pixel_font()   — 加载 VonwaonBitmap，返回字体族名
  pixel_font(size)    — 使用像素字体的 QFont
  PixelButton         — 双边框复古按钮（仅黑白配色）
  StarBackground      — 纯黑背景上的静态星空
"""

import os
import random
from typing import List, Tuple

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PyQt5.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.sound_manager import SoundManager

# ── 字体 ─────────────────────────────────────────────────────────────

_FONT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "font", "VonwaonBitmap-16px.ttf")
)
_PIXEL_FAMILY: str = ""


def load_pixel_font() -> str:
    """注册位图字体并返回其字体族名。"""
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
    """返回使用像素字体的 QFont；未加载时回退到 Courier New。"""
    family = _PIXEL_FAMILY or "Courier New"
    f = QFont(family, size)
    f.setBold(bold)
    return f


# ── 双边框像素按钮 ───────────────────────────────────────────────────

class PixelButton(QPushButton):
    """
    复古双边框按钮，与参考截图保持一致。

    普通：透明背景 · 白色双边框 · 白色文本
    悬停：白色背景 · 黑色双边框 · 黑色文本（动画）
    按下：与悬停一致，但略透明
    禁用：暗色边框和文本
    """

    _OUTER_R   = 10    # 外边框圆角半径（px）
    _GAP       = 5     # 外边框与内边框之间的间距（px）
    _BW        = 1.5   # 边框线宽
    _ANIM_STEP = 0.14  # 每 16 ms 帧的进度，完整过渡约 110 ms

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
        self._hover_progress: float = 0.0   # 0.0 = 普通，1.0 = 完全悬停
        self._silent = silent

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

        if not self._silent:
            self.clicked.connect(lambda: SoundManager.instance().play_click())

    # ── 动画 ─────────────────────────────────────────────────────────

    def _tick_anim(self) -> None:
        target = 1.0 if (self._hovered and self.isEnabled()) else 0.0
        if self._hover_progress < target:
            self._hover_progress = min(target, self._hover_progress + self._ANIM_STEP)
        else:
            self._hover_progress = max(target, self._hover_progress - self._ANIM_STEP)
        self.update()
        if self._hover_progress == target:
            self._anim_timer.stop()

    # ── 绘制 ─────────────────────────────────────────────────────────

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
            # 静态：纯黑填充，暗色边框/文本
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0))
            p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            bd = QColor(60, 60, 60)
            fg = QColor(70, 70, 70)
        elif pressed:
            # 静态：全白填充，黑色文本
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            bd = QColor(0, 0, 0)
            fg = QColor(0, 0, 0)
        else:
            # 动画：白色背景淡入，边框/文本从白色交叉淡变到黑色
            t = self._hover_progress
            bg_alpha = int(255 * t)
            if bg_alpha > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, bg_alpha))
                p.drawRoundedRect(QRectF(0, 0, w, h), OR, OR)
            v = int(255 * (1.0 - t))
            bd = QColor(v, v, v)
            fg = QColor(v, v, v)

        # 外边框
        p.setPen(QPen(bd, bw))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(bw / 2, bw / 2, w - bw, h - bw), OR, OR)

        # 内边框
        p.drawRoundedRect(QRectF(G, G, w - 2 * G, h - 2 * G), IR, IR)

        # 标签
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.text())

    # ── 悬停跟踪 ─────────────────────────────────────────────────────

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


# ── 星空 ─────────────────────────────────────────────────────────────

_Star = Tuple[float, float, int, int]   # (x 比例, y 比例, 像素尺寸, 亮度)


class StarBackground(QWidget):
    """
    静态星空控件（纯黑背景 + 微小白点）。
    星点使用确定性种子生成，因此每次显示都一致。
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


# ── 如可用则用 GPU shader 版本替换 StarBackground ─────────────────────
# home_screen.py / dialogs.py 都从这里导入 StarBackground；
# 在这里替换即可，无需改动其他位置。

try:
    from ui.shader_background import ShaderBackground as StarBackground  # noqa: F811
except Exception as _e:
    print(f"[pixel_widgets] ShaderBackground unavailable ({_e}), using static fallback")
