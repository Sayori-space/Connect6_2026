"""
AppWindow：顶层 QMainWindow。

包含一个拥有四个页面的 QStackedWidget：
  0 — HomeScreen    （主菜单）
  1 — GamePage      （实际棋局）
  2 — RulesScreen   （规则说明）
  3 — AIConfigPage  （AI 对局设置）

导航统一在这里处理；各页面只负责发出信号。
"""

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QGraphicsOpacityEffect, QMainWindow, QStackedWidget, QWidget,
)

import ui.theme as theme
from models.game_config import GameConfig
from models.player import PlayerType
from ui.ai_config_page import AIConfigPage
from ui.home_screen import HomeScreen
from ui.main_window import GamePage
from ui.rules_screen import RulesScreen


class _FadeOverlay(QWidget):
    """纯色遮罩层，250 ms 内淡出后自行销毁。

    在 setCurrentIndex 后立即放到 *新* 页面之上，因此即使离开的页面包含
    OpenGL 控件也能完成过渡（无需 grab()）。

    父对象设为 QStackedWidget，使其使用 stack 坐标。
    WA_TransparentForMouseEvents 保证动画期间底下的新页面仍可交互。
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

        # 将动画挂到 self 下，使其随控件一起销毁。
        # 这样 deleteLater 触发时可以干净清理。
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(250)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self.deleteLater)

    def start_fade(self) -> None:
        """启动淡出动画；应在 show() + raise_() 后调用。"""
        self._anim.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.BG))
        painter.end()


_PAGE_HOME     = 0
_PAGE_GAME     = 1
_PAGE_RULES    = 2
_PAGE_AI_CFG   = 3


class AppWindow(QMainWindow):
    """应用根窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("六子棋  ·  Connect Six")
        self.setStyleSheet(f"QMainWindow {{ background: {theme.BG}; }}")
        self.setMinimumSize(820, 620)
        self.resize(1000, 720)

        # ── 堆叠页面 ─────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home   = HomeScreen()
        self._game   = GamePage()
        self._rules  = RulesScreen()
        self._ai_cfg = AIConfigPage()

        self._stack.addWidget(self._home)    # 索引 0
        self._stack.addWidget(self._game)    # 索引 1
        self._stack.addWidget(self._rules)   # 索引 2
        self._stack.addWidget(self._ai_cfg)  # 索引 3

        # ── 信号连接 ─────────────────────────────────────────────────
        self._home.local_game_clicked.connect(self._start_local_game)
        self._home.ai_game_clicked.connect(self._show_ai_config)
        self._home.rules_clicked.connect(self._show_rules)
        self._home.quit_clicked.connect(self.close)

        self._game.go_home.connect(self._show_home)
        self._rules.go_back.connect(self._show_home)

        self._ai_cfg.go_back.connect(self._show_home)
        self._ai_cfg.game_config_ready.connect(self._launch_game)

        # 默认显示主界面
        self._stack.setCurrentIndex(_PAGE_HOME)

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #

    def _navigate(self, index: int) -> None:
        """切换到页面 `index`，并使用纯色淡入过渡。

        新页面会立即显示；与应用背景相同的纯色遮罩在其上方淡出，
        从而形成平滑观感，且无需对离开的页面执行 grab()
        （Windows 上含 QOpenGLWidget 的页面 grab() 会得到空白）。
        """
        if index == self._stack.currentIndex():
            return
        self._stack.setCurrentIndex(index)
        overlay = _FadeOverlay(parent=self._stack)
        overlay.setGeometry(self._stack.rect())
        overlay.show()
        overlay.raise_()
        overlay.start_fade()

    def _show_home(self) -> None:
        self._navigate(_PAGE_HOME)

    def _show_rules(self) -> None:
        self._navigate(_PAGE_RULES)

    def _show_ai_config(self) -> None:
        self._navigate(_PAGE_AI_CFG)

    def _start_local_game(self) -> None:
        config = GameConfig(
            black_type=PlayerType.HUMAN,
            white_type=PlayerType.HUMAN,
            black_name="黑方",
            white_name="白方",
        )
        self._launch_game(config)

    def _launch_game(self, config: GameConfig) -> None:
        self._navigate(_PAGE_GAME)   # 先切换页面，保证 UI 响应及时
        self._game.start_game(config)
