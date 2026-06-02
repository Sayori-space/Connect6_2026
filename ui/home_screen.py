"""
HomeScreen：主菜单。
与参考图一致：黑底星空、大号像素字体标题、居中的 PixelButton 按钮项。
按钮和标题会随窗口尺寸响应式缩放。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

import ui.theme as theme
from ui.pixel_widgets import PixelButton, StarBackground, pixel_font
from ui.sound_manager import SoundManager


class HomeScreen(QWidget):
    local_game_clicked = pyqtSignal()
    ai_game_clicked    = pyqtSignal()
    rules_clicked      = pyqtSignal()
    quit_clicked       = pyqtSignal()

    _REF_W = 1024
    _REF_H = 768

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self._bg = StarBackground(parent=self)
        self._bg.lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部留白 ─────────────────────────────────────────────────
        root.addStretch(3)

        # ── 标题 ─────────────────────────────────────────────────────
        self._title = QLabel("六子棋")
        self._title.setFont(pixel_font(36))
        self._title.setStyleSheet(f"color: {theme.FG}; background: transparent;")
        self._title.setAlignment(Qt.AlignCenter)
        root.addWidget(self._title)

        # ── 标题与按钮之间的比例间距 ─────────────────────────────────
        root.addStretch(2)

        # ── 按钮及其比例间距 ────────────────────────────────────────
        btn_defs = [
            ("本地双人对战", self.local_game_clicked),
            ("人机对战",     self.ai_game_clicked),
            ("规则讲解",     self.rules_clicked),
        ]

        self._buttons = []
        for i, (label, signal) in enumerate(btn_defs):
            btn = PixelButton(label, font_size=16)
            btn.setMinimumHeight(58)
            btn.setFixedWidth(320)
            btn.clicked.connect(signal)
            root.addWidget(btn, 0, Qt.AlignCenter)
            # 每个按钮后的间距（包括最后一个按钮之后）
            root.addStretch(1)
            self._buttons.append(btn)

        # 静音切换按钮
        self._mute_home_btn = PixelButton("音效: 开", font_size=16, silent=True)
        self._mute_home_btn.setMinimumHeight(58)
        self._mute_home_btn.setFixedWidth(320)
        self._mute_home_btn.clicked.connect(self._on_mute_clicked)
        root.addWidget(self._mute_home_btn, 0, Qt.AlignCenter)
        root.addStretch(1)
        self._buttons.append(self._mute_home_btn)

        # 退出按钮
        quit_btn = PixelButton("退出游戏", font_size=16)
        quit_btn.setMinimumHeight(58)
        quit_btn.setFixedWidth(320)
        quit_btn.clicked.connect(self.quit_clicked)
        root.addWidget(quit_btn, 0, Qt.AlignCenter)
        root.addStretch(1)
        self._buttons.append(quit_btn)

        # ── 底部留白 ─────────────────────────────────────────────────
        root.addStretch(2)

    def _on_mute_clicked(self) -> None:
        muted = SoundManager.instance().toggle_mute()
        self._mute_home_btn.setText("音效: 关" if muted else "音效: 开")

    def _apply_scale(self, w: int, h: int) -> None:
        scale = min(w / self._REF_W, h / self._REF_H)
        scale = max(0.75, min(2.8, scale))

        title_sz = max(22, int(36 * scale))
        btn_font = max(12, int(16 * scale))
        btn_w    = max(240, int(320 * scale))
        btn_h    = max(46,  int(58 * scale))

        self._title.setFont(pixel_font(title_sz))
        for btn in self._buttons:
            btn.setFont(pixel_font(btn_font))
            btn.setFixedWidth(btn_w)
            btn.setMinimumHeight(btn_h)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(self.rect())
        self._apply_scale(event.size().width(), event.size().height())
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))
