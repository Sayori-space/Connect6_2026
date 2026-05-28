"""
Dialogs – pixel-art styled modal windows.

AIConfigDialog matches the reference ChooseUi screenshot:
  • Star-field background
  • Two large stone-shape buttons for colour selection (Black / White)
  • Left/right arrow carousel for AI difficulty
  • PixelButton action buttons
"""

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

import ui.theme as theme
from models.game_config import GameConfig
from models.player import PlayerType
from ui.pixel_widgets import PixelButton, StarBackground, pixel_font


# ── Shared helper ──────────────────────────────────────────────────────

def _lbl(text: str, size: int = 14, dim: bool = False) -> QLabel:
    l = QLabel(text)
    l.setFont(pixel_font(size))
    col = theme.DIM if dim else theme.FG
    l.setStyleSheet(f"color: {col}; background: transparent;")
    l.setAlignment(Qt.AlignCenter)
    return l


# ── Stone-selector button ──────────────────────────────────────────────

class _StoneBtn(QPushButton):
    """Large rounded square that looks like a stone; toggles selected state."""

    SIZE = 64

    def __init__(self, stone_color: int, parent=None):
        super().__init__(parent)
        self._stone_color = stone_color   # BLACK=1, WHITE=2
        self._selected = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_selected(self, sel: bool) -> None:
        self._selected = sel
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.SIZE

        # Fill
        if self._stone_color == 1:   # black stone
            base = QColor(30, 30, 30)
        else:                         # white stone
            base = QColor(230, 230, 230)

        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawRoundedRect(0, 0, r, r, 14, 14)

        # Selection ring (golden yellow)
        if self._selected:
            pen = QPen(QColor(theme.WIN_GLOW), 3)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(2, 2, r - 4, r - 4, 12, 12)


# ── Difficulty carousel ────────────────────────────────────────────────

class _Carousel(QWidget):
    """◁ option ▷ selector."""

    def __init__(self, options: List[str], parent=None):
        super().__init__(parent)
        self._options = options
        self._index   = 0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._prev = PixelButton("◁", font_size=14)
        self._prev.setFixedSize(44, 44)
        self._prev.clicked.connect(self._go_prev)

        self._label = _lbl(options[0], size=13)
        self._label.setMinimumWidth(120)

        self._next = PixelButton("▷", font_size=14)
        self._next.setFixedSize(44, 44)
        self._next.clicked.connect(self._go_next)

        lay.addWidget(self._prev)
        lay.addWidget(self._label, 1)
        lay.addWidget(self._next)
        self._refresh()

    def _go_prev(self) -> None:
        self._index = (self._index - 1) % len(self._options)
        self._refresh()

    def _go_next(self) -> None:
        self._index = (self._index + 1) % len(self._options)
        self._refresh()

    def _refresh(self) -> None:
        self._label.setText(self._options[self._index])
        self._prev.setEnabled(len(self._options) > 1)
        self._next.setEnabled(len(self._options) > 1)

    @property
    def current(self) -> str:
        return self._options[self._index]


# ── Game-over dialog ───────────────────────────────────────────────────

class GameOverDialog(QDialog):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("游戏结束")
        self.setModal(True)
        self.setFixedSize(380, 220)
        self.setStyleSheet(f"background: {theme.BG};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 36, 36, 28)
        lay.setSpacing(20)

        lay.addWidget(_lbl(message, size=20))

        row = QHBoxLayout()
        row.setSpacing(16)

        again = PixelButton("再来一局", font_size=14)
        again.clicked.connect(self.accept)
        row.addWidget(again)

        close = PixelButton("关闭", font_size=14)
        close.clicked.connect(self.reject)
        row.addWidget(close)

        lay.addLayout(row)

    def paintEvent(self, _e) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))


# ── AI config dialog ───────────────────────────────────────────────────

class AIConfigDialog(QDialog):
    """
    Matches ChooseUi screenshot:
      star background · stone colour selector · AI difficulty carousel
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[GameConfig] = None
        self._selected_color = 1   # 1=BLACK(human plays black), 2=WHITE

        self.setWindowTitle("人机对战")
        self.setModal(True)
        self.setStyleSheet(f"background: {theme.BG};")
        # Scale with parent window; fall back to a sensible default
        if parent is not None:
            pw, ph = parent.width(), parent.height()
            w = max(480, min(680, int(pw * 0.42)))
            h = max(380, min(540, int(ph * 0.54)))
        else:
            w, h = 560, 440
        self.setFixedSize(w, h)

        # Star background
        self._bg = StarBackground(count=120, parent=self)
        self._bg.setGeometry(self.rect())
        self._bg.lower()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 24)
        lay.setSpacing(14)

        # Title
        lay.addWidget(_lbl("请选择颜色", size=14))

        # Stone buttons
        stone_row = QHBoxLayout()
        stone_row.setSpacing(24)
        stone_row.setAlignment(Qt.AlignCenter)

        self._black_btn = _StoneBtn(1)
        self._white_btn = _StoneBtn(2)
        self._black_btn.clicked.connect(lambda: self._pick(1))
        self._white_btn.clicked.connect(lambda: self._pick(2))
        stone_row.addWidget(self._black_btn)
        stone_row.addWidget(self._white_btn)
        lay.addLayout(stone_row)
        self._pick(1)   # default: human plays black

        # AI difficulty
        lay.addWidget(_lbl("AI难度预设", size=13, dim=True))
        self._carousel = _Carousel(["随机AI"])   # extend list for more AI levels
        lay.addWidget(self._carousel, 0, Qt.AlignCenter)

        lay.addStretch(1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        back_btn = PixelButton("返回", font_size=13)
        back_btn.clicked.connect(self.reject)
        btn_row.addWidget(back_btn)

        start_btn = PixelButton("开始游戏", font_size=13)
        start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(start_btn)

        lay.addLayout(btn_row)

    def _pick(self, color: int) -> None:
        self._selected_color = color
        self._black_btn.set_selected(color == 1)
        self._white_btn.set_selected(color == 2)

    def _on_start(self) -> None:
        if self._selected_color == 1:   # human plays black
            self._result = GameConfig(
                black_type=PlayerType.HUMAN, white_type=PlayerType.AI,
                black_name="玩家", white_name="AI",
            )
        else:                            # human plays white
            self._result = GameConfig(
                black_type=PlayerType.AI, white_type=PlayerType.HUMAN,
                black_name="AI", white_name="玩家",
            )
        self.accept()

    @property
    def config(self) -> GameConfig:
        return self._result or GameConfig()

    def paintEvent(self, _e) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))


# ── New game dialog (local) ────────────────────────────────────────────

class NewGameDialog(QDialog):
    def __init__(self, current_config: GameConfig, parent=None):
        super().__init__(parent)
        self._result: Optional[GameConfig] = None
        self.setWindowTitle("新游戏")
        self.setModal(True)
        self.setFixedSize(380, 240)
        self.setStyleSheet(f"background: {theme.BG};")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(14)

        lay.addWidget(_lbl("模式选择", size=16))

        self._carousel = _Carousel(["双人对战", "黑方AI", "白方AI", "AI对战"])
        lay.addWidget(self._carousel, 0, Qt.AlignCenter)

        lay.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(16)

        cancel = PixelButton("取消", font_size=13)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        start = PixelButton("开始", font_size=13)
        start.clicked.connect(self._on_start)
        row.addWidget(start)

        lay.addLayout(row)

    def _on_start(self) -> None:
        mode = self._carousel.current
        mapping = {
            "双人对战": (PlayerType.HUMAN, PlayerType.HUMAN, "黑方", "白方"),
            "黑方AI":   (PlayerType.AI,    PlayerType.HUMAN, "AI",   "玩家"),
            "白方AI":   (PlayerType.HUMAN, PlayerType.AI,    "玩家", "AI"),
            "AI对战":   (PlayerType.AI,    PlayerType.AI,    "AI黑", "AI白"),
        }
        bt, wt, bn, wn = mapping[mode]
        self._result = GameConfig(
            black_type=bt, white_type=wt,
            black_name=bn, white_name=wn,
        )
        self.accept()

    @property
    def config(self) -> GameConfig:
        return self._result or GameConfig()

    def paintEvent(self, _e) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))
