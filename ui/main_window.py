"""
GamePage – the in-game screen.

Converted from QMainWindow to QWidget so it can be embedded inside the
AppWindow's QStackedWidget.  All game logic remains in GameManager; this
class is purely responsible for wiring UI signals to game-manager calls
and feeding callbacks back to the UI.
"""

from typing import Dict, List, Optional, Tuple

import os

from PyQt5.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QHBoxLayout, QWidget

from ai.base_ai import BaseAI
from ai.factory import build_ai
from ui.sound_manager import SoundManager
from game.game_manager import GameManager, GameState
from models.game_config import GameConfig
from models.move import Move
from models.player import PlayerType
from ui.board_widget import BoardWidget
from ui.control_panel import ControlPanel
from ui.dialogs import GameOverDialog
from utils.chess_manual import (
    DEFAULT_BLACK_EXPORT_NAME,
    DEFAULT_WHITE_EXPORT_NAME,
    build_chess_manual_filename,
    build_chess_manual_record,
)
from utils.constants import BLACK, WHITE


def _make_ai(config: GameConfig) -> "BaseAI":
    """Create AI instance for the given config."""
    return build_ai(config)


class GamePage(QWidget):
    """The full game screen (board + sidebar).  Embedded in AppWindow."""

    go_home = pyqtSignal()   # user wants to return to the home screen

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._manager: Optional[GameManager] = None
        self._ai: Dict[int, BaseAI] = {}

        # Delayed AI move timer
        self._ai_timer = QTimer(self)
        self._ai_timer.setSingleShot(True)
        self._ai_timer.timeout.connect(self._execute_ai_move)
        self._pending_ai_color: Optional[int] = None

        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        import ui.theme as _theme
        self.setStyleSheet(f"background: {_theme.BG};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._board = BoardWidget()
        self._board.stone_clicked.connect(self._on_stone_clicked)
        self._board.undo_requested.connect(self._on_undo_stone_requested)
        # Board takes 4 parts; panel takes 1 part → panel ≈ 20 % of width
        layout.addWidget(self._board, 4)

        self._panel = ControlPanel()
        self._panel.confirm_requested.connect(self._on_confirm_requested)
        self._panel.undo_stone_requested.connect(self._on_undo_stone_requested)
        self._panel.undo_turn_requested.connect(self._on_undo_turn_requested)
        self._panel.save_manual_requested.connect(self._on_save_manual_requested)
        self._panel.go_home_requested.connect(self.go_home)
        layout.addWidget(self._panel, 1)

    # ------------------------------------------------------------------ #
    # Public API (called by AppWindow)
    # ------------------------------------------------------------------ #

    def start_game(self, config: GameConfig) -> None:
        """Initialise / reinitialise the game with the given config."""
        self._ai_timer.stop()
        self._pending_ai_color = None

        ai: Dict[int, BaseAI] = {}
        if config.black_type == PlayerType.AI:
            ai[BLACK] = _make_ai(config)
        if config.white_type == PlayerType.AI:
            ai[WHITE] = _make_ai(config)
        self._finish_start_game(config, ai)

    def _finish_start_game(self, config: GameConfig, ai: Dict[int, BaseAI]) -> None:
        """Complete game setup once AI instances are ready."""
        self._ai = ai

        # Create GameManager and wire callbacks
        self._manager = GameManager(config)
        self._manager.on_stone_placed    = self._cb_stone_placed
        self._manager.on_turn_changed    = self._cb_turn_changed
        self._manager.on_game_over       = self._cb_game_over
        self._manager.on_undo            = self._cb_undo
        self._manager.on_request_ai_move = self._cb_request_ai_move
        self._manager.on_confirm_needed  = self._cb_confirm_needed
        self._manager.on_stone_removed   = self._cb_stone_removed

        # Reset UI
        self._board.set_board(self._manager.board)
        self._board.clear_winning_line()
        self._board.set_interactive(False)
        self._panel.reset_for_new_game()
        self._panel.set_player_names(config.black_name, config.white_name)

        self._manager.start()

    # ------------------------------------------------------------------ #
    # UI signal handlers
    # ------------------------------------------------------------------ #

    @pyqtSlot(int, int)
    def _on_stone_clicked(self, row: int, col: int) -> None:
        if self._manager is None:
            return
        if self._manager.current_player.player_type != PlayerType.HUMAN:
            return
        self._manager.try_place(row, col)

    @pyqtSlot()
    def _on_confirm_requested(self) -> None:
        if self._manager:
            self._manager.confirm_turn()

    @pyqtSlot()
    def _on_undo_stone_requested(self) -> None:
        """Remove the last stone placed in the current turn."""
        if self._manager is None:
            return
        # Only allow undo-stone when it's a human's turn
        if self._manager.current_player.player_type != PlayerType.HUMAN:
            return
        if self._manager.undo_last_stone():
            # Hide confirm button (may have been visible)
            self._panel.show_confirm_button(False)
            self._board.set_interactive(True)
            self._board.update()
            if self._manager:
                self._panel.update_stones_placed(
                    self._manager.stones_placed_this_turn,
                    self._manager.stones_needed_this_turn,
                )

    @pyqtSlot()
    def _on_undo_turn_requested(self) -> None:
        """Roll back one complete turn."""
        if self._manager is None:
            return
        # Cancel any pending AI move
        self._ai_timer.stop()
        self._pending_ai_color = None
        self._manager.undo()

    @pyqtSlot()
    def _on_save_manual_requested(self) -> None:
        if not self._manager:
            return
        history = self._manager.board.history
        if not history:
            return

        chess_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "chess_manual")
        )
        os.makedirs(chess_dir, exist_ok=True)
        filename = build_chess_manual_filename(
            chess_dir,
            DEFAULT_BLACK_EXPORT_NAME,
            DEFAULT_WHITE_EXPORT_NAME,
            self._manager.winner,
        )
        filepath = os.path.join(chess_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(build_chess_manual_record(history, self._manager.winner))
        print(f"[GamePage] 棋谱已保存: {filepath}")

    # ------------------------------------------------------------------ #
    # GameManager callbacks
    # ------------------------------------------------------------------ #

    def _cb_stone_placed(self, move: Move) -> None:
        self._board.animate_stone(move)
        SoundManager.instance().play_stone()
        if self._manager:
            self._panel.update_stones_placed(
                self._manager.stones_placed_this_turn,
                self._manager.stones_needed_this_turn,
            )
            self._update_current_turn_highlight()

    def _cb_confirm_needed(self) -> None:
        """Human has placed all required stones – show the Confirm button."""
        self._board.set_interactive(False)   # no more left-clicks until confirmed
        self._panel.show_confirm_button(True)
        self._panel.update_stones_placed(
            self._manager.stones_needed_this_turn,
            self._manager.stones_needed_this_turn,
        )

    def _cb_stone_removed(self, move: Move) -> None:
        """A stone was undone via undo_last_stone."""
        self._board.update()
        self._update_current_turn_highlight()

    def _cb_turn_changed(self, color: int, stones_needed: int) -> None:
        is_human = (
            self._manager is not None
            and self._manager.current_player.player_type == PlayerType.HUMAN
        )
        self._board.set_hover_color(color)
        self._board.set_interactive(is_human)
        self._panel.show_confirm_button(False)
        self._panel.update_turn(color, stones_needed)

        # Update AI info display
        if color in self._ai:
            self._panel.set_ai_info(self._ai[color].name)
        else:
            self._panel.set_ai_info("")

        # Do NOT clear the highlight here — keep the last turn's stones lit
        # until the new turn's first stone is placed.

    def _cb_game_over(
        self, winner: Optional[int], line: List[Tuple[int, int]]
    ) -> None:
        self._board.set_interactive(False)
        self._panel.show_confirm_button(False)
        self._board.set_current_turn_stones([])
        if line:
            self._board.show_winning_line(line)

        if winner is None:
            message = "平局！"
        elif winner == BLACK:
            name = self._manager.players[BLACK].name if self._manager else "黑方"
            message = f"{name} 获胜！"
        else:
            name = self._manager.players[WHITE].name if self._manager else "白方"
            message = f"{name} 获胜！"

        self._panel.update_game_over(winner, message)
        QTimer.singleShot(1400, lambda: self._show_game_over_dialog(message))

    def _show_game_over_dialog(self, message: str) -> None:
        dialog = GameOverDialog(message, self)
        result = dialog.exec_()
        if result == GameOverDialog.Accepted and self._manager:
            self.start_game(self._manager.config)

    def _cb_undo(self, undone: List[Move]) -> None:
        self._board.update()
        if self._manager:
            color  = self._manager.current_color
            needed = self._manager.stones_needed_this_turn
            is_human = self._manager.current_player.player_type == PlayerType.HUMAN
            self._board.set_hover_color(color)
            self._board.set_interactive(is_human)
            self._panel.show_confirm_button(False)
            self._panel.update_turn(color, needed)
        self._update_current_turn_highlight()

    def _update_current_turn_highlight(self) -> None:
        cells = [(m.row, m.col) for m in self._manager.pending_moves] \
                if self._manager else []
        self._board.set_current_turn_stones(cells)

    def _cb_request_ai_move(self, color: int) -> None:
        self._pending_ai_color = color
        self._ai_timer.start(440)

    # ------------------------------------------------------------------ #
    # AI execution
    # ------------------------------------------------------------------ #

    def _execute_ai_move(self) -> None:
        if self._manager is None or self._pending_ai_color is None:
            return
        color = self._pending_ai_color
        ai = self._ai.get(color)
        if ai is None:
            return

        count = self._manager.stones_needed_this_turn
        moves = ai.get_moves(self._manager.board.copy(), color, count)

        for move in moves:
            self._manager.try_place(move.row, move.col)
            if self._manager.state == GameState.GAME_OVER:
                break
