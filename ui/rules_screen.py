"""
RulesScreen：六子棋规则说明页。
像素独立游戏风格：黑色背景、白色像素字体文本、PixelButton 返回按钮。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QWidget,
)

import ui.theme as theme
from ui.pixel_widgets import PixelButton, pixel_font


# ── 规则内容 ─────────────────────────────────────────────────────────

_SECTIONS = [
    ("基本介绍", [
        "六子棋（Connect Six）由台湾交通大学吴毅成教授于 2003 年发明。",
        "双人策略棋盘游戏，规则简单，策略深邃。",
    ]),
    ("棋盘", [
        "标准棋盘为 19 × 19，共 361 个交叉点。",
        "黑方执黑棋，白方执白棋。",
    ]),
    ("落子规则", [
        "第一回合（黑方先手）：仅落 1 颗棋子。",
        "此后每个回合：双方各落 2 颗棋子，可下在棋盘任意两个空交叉点。",
        "落子后点击「确定落子」按钮方才生效，确认前可撤回。",
    ]),
    ("胜利条件", [
        "率先在横、竖或斜方向形成连续 6 子的一方获胜。",
        "超过 6 子的连线同样算赢，无上限。",
        "无禁手：六子棋不设任何禁手规则。",
    ]),
    ("公平性", [
        "黑方首回合仅落 1 子，平衡了先手优势，双方胜率接近均等。",
        "理论上，在无限大棋盘上六子棋是平局。",
    ]),
    ("界面操作", [
        "左键单击：在该交叉点落子。",
        "右键单击 / 撤回棋子：撤回本回合最后一颗棋子（确认前有效）。",
        "确定落子：落完本回合所有棋子后点击，轮到对方。",
        "悔棋：回退至上一个完整回合。",
        "认输：当前玩家放弃本局。",
    ]),
]


def _section_widget() -> QWidget:
    """用像素标签构建完整规则内容 QWidget。"""
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    heading_font = pixel_font(20)
    body_font    = pixel_font(16)

    for title, lines in _SECTIONS:
        # 小节标题
        h = QLabel(f"[ {title} ]")
        h.setFont(heading_font)
        h.setStyleSheet(f"color: {theme.FG}; background: transparent;")
        h.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(h)
        lay.addSpacing(10)

        # 项目符号文本行
        for line in lines:
            b = QLabel(f"  ▸  {line}")
            b.setFont(body_font)
            b.setStyleSheet(f"color: {theme.DIM}; background: transparent;")
            b.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            b.setWordWrap(True)
            lay.addWidget(b)
            lay.addSpacing(8)

        lay.addSpacing(28)

    lay.addStretch(1)
    return container


# ── 页面 ─────────────────────────────────────────────────────────────

class RulesScreen(QWidget):
    go_back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 标题 ─────────────────────────────────────────────────────
        title = QLabel("六子棋  规则讲解")
        title.setFont(pixel_font(30))
        title.setStyleSheet(f"color: {theme.FG}; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(96)
        root.addWidget(title)

        # ── 可滚动内容 ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {theme.BG}; border: none; }}
            QScrollBar:vertical {{
                background: #111111;
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.DIM};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        content = _section_widget()
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background: {theme.BG};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(80, 32, 80, 32)
        wl.addWidget(content)

        scroll.setWidget(wrapper)
        root.addWidget(scroll, 1)

        # ── 页脚 / 返回按钮 ──────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(80)
        footer.setStyleSheet(f"background: {theme.BG};")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(48, 12, 48, 12)

        back_btn = PixelButton("← 返回主页", font_size=15)
        back_btn.setFixedWidth(240)
        back_btn.setFixedHeight(48)
        back_btn.clicked.connect(self.go_back)
        fl.addWidget(back_btn, 0, Qt.AlignLeft | Qt.AlignVCenter)

        root.addWidget(footer)

    def paintEvent(self, _e) -> None:
        QPainter(self).fillRect(self.rect(), QColor(theme.BG))
