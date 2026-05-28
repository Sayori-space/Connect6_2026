"""
AppWindow – the top-level QMainWindow.

Contains a QStackedWidget with four pages:
  0 – HomeScreen    (main menu)
  1 – GamePage      (the actual board game)
  2 – RulesScreen   (rules explanation)
  3 – AIConfigPage  (AI game setup)

Navigation is handled here; individual pages only emit signals.
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
    """Solid-colour overlay that fades out over 250 ms then self-destructs.

    Placed on top of the *new* page immediately after setCurrentIndex so the
    transition works regardless of whether the departing page contained an
    OpenGL widget (no grab() needed).

    Parented to the QStackedWidget so it lives in stack coordinates.
    WA_TransparentForMouseEvents ensures the new page beneath is interactive
    during the animation.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

        # Parent the animation to self so it is destroyed with the widget.
        # This ensures clean cleanup when deleteLater fires.
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(250)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self.deleteLater)

    def start_fade(self) -> None:
        """Start the fade-out animation. Call after show() + raise_()."""
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
    """Root application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("六子棋  ·  Connect Six")
        self.setStyleSheet(f"QMainWindow {{ background: {theme.BG}; }}")
        self.setMinimumSize(820, 620)
        self.resize(1000, 720)

        # ── Stacked pages ─────────────────────────────────────────────
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home   = HomeScreen()
        self._game   = GamePage()
        self._rules  = RulesScreen()
        self._ai_cfg = AIConfigPage()

        self._stack.addWidget(self._home)    # index 0
        self._stack.addWidget(self._game)    # index 1
        self._stack.addWidget(self._rules)   # index 2
        self._stack.addWidget(self._ai_cfg)  # index 3

        # ── Signal wiring ─────────────────────────────────────────────
        self._home.local_game_clicked.connect(self._start_local_game)
        self._home.ai_game_clicked.connect(self._show_ai_config)
        self._home.rules_clicked.connect(self._show_rules)
        self._home.quit_clicked.connect(self.close)

        self._game.go_home.connect(self._show_home)
        self._rules.go_back.connect(self._show_home)

        self._ai_cfg.go_back.connect(self._show_home)
        self._ai_cfg.game_config_ready.connect(self._launch_game)

        # Start on the home screen
        self._stack.setCurrentIndex(_PAGE_HOME)

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _navigate(self, index: int) -> None:
        """Switch to page `index` with a solid-colour fade-in transition.

        The new page is shown immediately; a solid overlay (matching the app
        background) fades out on top of it, giving a smooth appearance without
        requiring a grab() of the departing page (which would be blank for
        pages that contain a QOpenGLWidget on Windows).
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
        self._navigate(_PAGE_GAME)   # switch first so UI is responsive
        self._game.start_game(config)
