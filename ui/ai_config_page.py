"""
AIConfigPage – full-screen AI game setup page.

Replaces the AIConfigDialog popup so the config lives in the
AppWindow QStackedWidget as a proper page.
"""

from typing import List, Optional

from PyQt5.QtCore import (
    QEasingCurve, QEvent, QPropertyAnimation, QRectF,
    Qt, pyqtProperty, pyqtSignal, QTimer,
)
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout, QPushButton, QVBoxLayout, QWidget, QLabel,
)

import ui.theme as theme
from models.game_config import GameConfig
from models.player import PlayerType
from ui.pixel_widgets import PixelButton, StarBackground, pixel_font


AI_OPTIONS = ("剪枝AI", "alpha-belta-plus", "alpha-belta-max")
THINK_TIME_OPTIONS = (("0.5s", 0.5), ("1.0s", 1.0), ("2.5s", 2.5), ("5.0s", 5.0))


def _ai_type_from_label(label: str) -> str:
    if label == "剪枝AI":
        return "alpha_beta"
    if label == "alpha-belta-plus":
        return "alpha_belta_plus"
    if label == "alpha-belta-max":
        return "alpha_belta_max"
    raise ValueError(f"unsupported AI label: {label}")


def _think_time_seconds_from_label(label: str) -> float:
    for option_label, seconds in THINK_TIME_OPTIONS:
        if option_label == label:
            return seconds
    raise ValueError(f"unsupported think time label: {label}")


def _build_ai_game_config(
    selected_color: int,
    ai_label: str,
    think_time_label: str,
) -> GameConfig:
    ai_type = _ai_type_from_label(ai_label)
    think_time_seconds = _think_time_seconds_from_label(think_time_label)
    if selected_color == 1:
        return GameConfig(
            black_type=PlayerType.HUMAN,
            white_type=PlayerType.AI,
            black_name="玩家",
            white_name="AI",
            ai_type=ai_type,
            ai_think_time_seconds=think_time_seconds,
        )
    return GameConfig(
        black_type=PlayerType.AI,
        white_type=PlayerType.HUMAN,
        black_name="AI",
        white_name="玩家",
        ai_type=ai_type,
        ai_think_time_seconds=think_time_seconds,
    )


# ── Stone-selector button ───────────────────────────────────────────────

class _StoneBtn(QPushButton):
    """
    Stone-shaped selector with elastic jelly hover-scale animation.

    The widget is padded by _PAD on each side so the elastic overshoot
    (scale > 1.0) never clips at the widget boundary.
    """

    _PAD = 24   # extra room around the stone for animation overshoot

    def __init__(self, stone_color: int, size: int = 64, parent=None):
        super().__init__(parent)
        self._stone_color = stone_color
        self._selected    = False
        self._sz          = size
        self._s           = 1.0      # current draw-scale (backing store)

        self.setFixedSize(size + self._PAD, size + self._PAD)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self._anim = QPropertyAnimation(self, b"_anim_scale")

    # ── pyqtProperty so QPropertyAnimation can animate _s ───────────

    def _get_s(self) -> float:
        return self._s

    def _set_s(self, v: float) -> None:
        self._s = v
        self.update()

    _anim_scale = pyqtProperty(float, _get_s, _set_s)

    # ── Public API ───────────────────────────────────────────────────

    def set_selected(self, sel: bool) -> None:
        self._selected = sel
        self.update()

    def resize_to(self, size: int) -> None:
        self._sz = size
        self.setFixedSize(size + self._PAD, size + self._PAD)
        self.update()

    # ── Hover events ─────────────────────────────────────────────────

    def event(self, e) -> bool:
        if e.type() == QEvent.HoverEnter:
            self._anim.stop()
            self._anim.setStartValue(self._s)
            self._anim.setEndValue(1.18)
            self._anim.setEasingCurve(QEasingCurve.OutElastic)
            self._anim.setDuration(560)
            self._anim.start()
        elif e.type() == QEvent.HoverLeave:
            self._anim.stop()
            self._anim.setStartValue(self._s)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.setDuration(280)
            self._anim.start()
        return super().event(e)

    # ── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        s    = self._s
        half = self._sz * s / 2
        side = self._sz * s
        x, y = cx - half, cy - half
        cr   = 14.0 * s

        base = QColor(30, 30, 30) if self._stone_color == 1 else QColor(230, 230, 230)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawRoundedRect(QRectF(x, y, side, side), cr, cr)

        if self._selected:
            p.setPen(QPen(QColor(theme.WIN_GLOW), 3))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(
                QRectF(x + 2, y + 2, side - 4, side - 4),
                max(1.0, cr - 2), max(1.0, cr - 2),
            )


# ── Carousel arrow button ────────────────────────────────────────────────

class _ArrowBtn(QPushButton):
    """
    Minimal transparent arrow button for the difficulty carousel.

    Normal   : transparent bg · white text
    Hover    : white fill (animated) · black text
    Disabled : transparent bg · dim text  (no black fill)
    """

    _ANIM_STEP = 0.14

    def __init__(self, text: str, font_size: int = 14, parent=None):
        super().__init__(text, parent)
        self.setFont(pixel_font(font_size))
        self.setAttribute(Qt.WA_Hover, True)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)

        self._hovered         = False
        self._hover_progress  = 0.0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._tick_anim)

    def _tick_anim(self) -> None:
        target = 1.0 if (self._hovered and self.isEnabled()) else 0.0
        if self._hover_progress < target:
            self._hover_progress = min(target, self._hover_progress + self._ANIM_STEP)
        else:
            self._hover_progress = max(target, self._hover_progress - self._ANIM_STEP)
        self.update()
        if self._hover_progress == target:
            self._anim_timer.stop()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        if not self.isEnabled():
            p.setPen(QColor(70, 70, 70))
            p.setFont(self.font())
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.text())
            return

        t = self._hover_progress
        if t > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, int(255 * t)))
            p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        v = int(255 * (1.0 - t))
        p.setPen(QColor(v, v, v))
        p.setFont(self.font())
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.text())

    def event(self, e) -> bool:
        if e.type() == QEvent.HoverEnter:
            self._hovered = True
            self._anim_timer.start()
        elif e.type() == QEvent.HoverLeave:
            self._hovered = False
            self._anim_timer.start()
        return super().event(e)


# ── Difficulty carousel ─────────────────────────────────────────────────

class _Carousel(QWidget):
    def __init__(self, options: List[str], parent=None):
        super().__init__(parent)
        self._options        = options
        self._index          = 0
        self._pending_index: Optional[int] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._prev = _ArrowBtn("◁", font_size=14)
        self._prev.setFixedSize(44, 44)
        self._prev.clicked.connect(self._go_prev)

        self._label = QLabel(options[0])
        self._label.setFont(pixel_font(13))
        self._label.setStyleSheet(f"color: {theme.FG}; background: transparent;")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMinimumWidth(120)

        self._next = _ArrowBtn("▷", font_size=14)
        self._next.setFixedSize(44, 44)
        self._next.clicked.connect(self._go_next)

        lay.addWidget(self._prev)
        lay.addWidget(self._label, 1)
        lay.addWidget(self._next)

        # Opacity fade animation for label text transitions
        self._opacity_fx = QGraphicsOpacityEffect(self._label)
        self._label.setGraphicsEffect(self._opacity_fx)

        self._fade_out = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_out.setDuration(100)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self._on_fade_out_done)

        self._fade_in = QPropertyAnimation(self._opacity_fx, b"opacity")
        self._fade_in.setDuration(150)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._refresh_buttons()

    # ── Navigation ───────────────────────────────────────────────────

    def _go_prev(self) -> None:
        self._pending_index = (self._index - 1) % len(self._options)
        self._fade_out.start()

    def _go_next(self) -> None:
        self._pending_index = (self._index + 1) % len(self._options)
        self._fade_out.start()

    def _on_fade_out_done(self) -> None:
        if self._pending_index is not None:
            self._index         = self._pending_index
            self._pending_index = None
        self._label.setText(self._options[self._index])
        self._fade_in.start()

    def _refresh_buttons(self) -> None:
        enabled = len(self._options) > 1
        self._prev.setEnabled(enabled)
        self._next.setEnabled(enabled)

    # ── Responsive scaling ───────────────────────────────────────────

    def set_scale(self, scale: float) -> None:
        self._label.setFont(pixel_font(max(10, int(13 * scale))))
        btn_sz = max(36, int(44 * scale))
        self._prev.setFixedSize(btn_sz, btn_sz)
        self._next.setFixedSize(btn_sz, btn_sz)
        fnt_sz = max(10, int(14 * scale))
        self._prev.setFont(pixel_font(fnt_sz))
        self._next.setFont(pixel_font(fnt_sz))

    @property
    def current(self) -> str:
        return self._options[self._index]


# ── Label helper ────────────────────────────────────────────────────────

def _lbl(text: str, size: int = 14, dim: bool = False) -> QLabel:
    l = QLabel(text)
    l.setFont(pixel_font(size))
    col = theme.DIM if dim else theme.FG
    l.setStyleSheet(f"color: {col}; background: transparent;")
    l.setAlignment(Qt.AlignCenter)
    return l


# ── Page widget ─────────────────────────────────────────────────────────

class AIConfigPage(QWidget):
    """Full-page AI game setup; emits signals instead of returning from exec_."""

    game_config_ready = pyqtSignal(object)   # GameConfig
    go_back           = pyqtSignal()

    _REF_W = 1024
    _REF_H = 768

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_color = 1   # 1=BLACK (human plays black)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self._bg = StarBackground(parent=self)
        self._bg.lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addStretch(3)

        self._title_lbl = _lbl("人机对战", size=28)
        root.addWidget(self._title_lbl, 0, Qt.AlignCenter)
        root.addStretch(1)

        self._color_hint_lbl = _lbl("请选择执棋颜色", size=14, dim=True)
        root.addWidget(self._color_hint_lbl, 0, Qt.AlignCenter)
        root.addStretch(1)

        # Stone selector row
        stone_row = QHBoxLayout()
        stone_row.setSpacing(40)
        stone_row.setAlignment(Qt.AlignCenter)

        self._black_btn = _StoneBtn(1, size=96)
        self._white_btn = _StoneBtn(2, size=96)

        black_wrap = QVBoxLayout()
        black_wrap.setSpacing(8)
        black_wrap.addWidget(self._black_btn, 0, Qt.AlignCenter)
        self._black_name_lbl = _lbl("执黑先行", size=12)
        black_wrap.addWidget(self._black_name_lbl, 0, Qt.AlignCenter)

        white_wrap = QVBoxLayout()
        white_wrap.setSpacing(8)
        white_wrap.addWidget(self._white_btn, 0, Qt.AlignCenter)
        self._white_name_lbl = _lbl("执白后手", size=12)
        white_wrap.addWidget(self._white_name_lbl, 0, Qt.AlignCenter)

        stone_row.addLayout(black_wrap)
        stone_row.addLayout(white_wrap)
        root.addLayout(stone_row)
        root.addStretch(1)

        self._black_btn.clicked.connect(lambda: self._pick(1))
        self._white_btn.clicked.connect(lambda: self._pick(2))
        self._pick(1)

        self._diff_lbl = _lbl("AI 难度预设", size=13, dim=True)
        root.addWidget(self._diff_lbl, 0, Qt.AlignCenter)
        self._carousel = _Carousel(list(AI_OPTIONS))
        root.addWidget(self._carousel, 0, Qt.AlignCenter)
        root.addStretch(1)

        self._think_time_lbl = _lbl("AI 思考时间", size=13, dim=True)
        root.addWidget(self._think_time_lbl, 0, Qt.AlignCenter)
        self._think_time_carousel = _Carousel(
            [label for label, _seconds in THINK_TIME_OPTIONS]
        )
        root.addWidget(self._think_time_carousel, 0, Qt.AlignCenter)

        root.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)

        self._back_btn = PixelButton("返回主界面", font_size=14)
        self._back_btn.setFixedWidth(200)
        self._back_btn.clicked.connect(self.go_back)
        btn_row.addWidget(self._back_btn)

        self._start_btn = PixelButton("开始游戏", font_size=14)
        self._start_btn.setFixedWidth(200)
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        root.addLayout(btn_row)
        root.addStretch(2)

    # ── Responsive scaling ──────────────────────────────────────────────

    def _apply_scale(self, w: int, h: int) -> None:
        scale = min(w / self._REF_W, h / self._REF_H)
        scale = max(0.75, min(2.5, scale))

        self._title_lbl.setFont(pixel_font(max(18, int(28 * scale))))
        self._color_hint_lbl.setFont(pixel_font(max(10, int(14 * scale))))
        self._black_name_lbl.setFont(pixel_font(max(9, int(12 * scale))))
        self._white_name_lbl.setFont(pixel_font(max(9, int(12 * scale))))
        self._diff_lbl.setFont(pixel_font(max(10, int(13 * scale))))
        self._think_time_lbl.setFont(pixel_font(max(10, int(13 * scale))))

        stone_sz = max(72, int(96 * scale))
        self._black_btn.resize_to(stone_sz)
        self._white_btn.resize_to(stone_sz)

        self._carousel.set_scale(scale)
        self._think_time_carousel.set_scale(scale)

        btn_font = max(11, int(14 * scale))
        btn_w    = max(150, int(200 * scale))
        btn_h    = max(40,  int(48 * scale))
        for btn in (self._back_btn, self._start_btn):
            btn.setFont(pixel_font(btn_font))
            btn.setFixedWidth(btn_w)
            btn.setMinimumHeight(btn_h)

    # ── Logic ───────────────────────────────────────────────────────────

    def _pick(self, color: int) -> None:
        self._selected_color = color
        self._black_btn.set_selected(color == 1)
        self._white_btn.set_selected(color == 2)

    def _on_start(self) -> None:
        config = _build_ai_game_config(
            selected_color=self._selected_color,
            ai_label=self._carousel.current,
            think_time_label=self._think_time_carousel.current,
        )
        self.game_config_ready.emit(config)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(self.rect())
        self._apply_scale(event.size().width(), event.size().height())
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))
