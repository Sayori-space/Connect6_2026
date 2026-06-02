"""
GamePage：对局中的游戏界面。

已从 QMainWindow 改为 QWidget，便于嵌入 AppWindow 的 QStackedWidget。
所有游戏逻辑仍保留在 GameManager 中；本类只负责把 UI 信号连接到
game-manager 调用，并把回调结果反馈给 UI。
"""

from typing import Dict, List, Optional, Tuple

import os
import time

from PyQt5.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QHBoxLayout, QWidget

from ai.base_ai import BaseAI
from ai.factory import build_ai
from ai.time_control import allocate_ai_move_time
from ui.sound_manager import SoundManager
from game.game_manager import GameManager, GameState
from models.game_config import GameConfig
from models.move import Move
from models.player import PlayerType
from ui.board_widget import BoardWidget
from ui.control_panel import ControlPanel
from ui.dialogs import GameOverDialog
from utils.chess_manual import (
    build_chess_manual_filename,
    build_chess_manual_record,
)
from utils.constants import BLACK, WHITE


def _make_ai(config: GameConfig) -> "BaseAI":
    """根据给定配置创建 AI 实例。"""
    return build_ai(config)


class _AiMoveWorker(QObject):
    finished = pyqtSignal(int, int, object)

    def __init__(
        self,
        request_id: int,
        ai: BaseAI,
        board,
        color: int,
        count: int,
    ):
        super().__init__()
        self._request_id = request_id
        self._ai = ai
        self._board = board
        self._color = color
        self._count = count

    @pyqtSlot()
    def run(self) -> None:
        try:
            moves = self._ai.get_moves(self._board, self._color, self._count)
        except Exception as exc:
            print(f"[GamePage] AI move failed: {exc}")
            moves = []
        self.finished.emit(self._request_id, self._color, moves)


class GamePage(QWidget):
    """完整游戏界面（棋盘 + 侧边栏），嵌入 AppWindow。"""

    go_home = pyqtSignal()   # 用户希望返回主界面

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._manager: Optional[GameManager] = None
        self._ai: Dict[int, BaseAI] = {}

        # 延迟触发 AI 落子的定时器
        self._ai_timer = QTimer(self)
        self._ai_timer.setSingleShot(True)
        self._ai_timer.timeout.connect(self._execute_ai_move)
        self._pending_ai_color: Optional[int] = None
        self._ai_request_id = 0
        self._ai_threads: List[QThread] = []
        self._ai_workers: List[_AiMoveWorker] = []
        self._ai_time_remaining: Dict[int, float] = {}
        self._active_ai_color: Optional[int] = None
        self._active_ai_started_at: Optional[float] = None
        self._ai_countdown_timer = QTimer(self)
        self._ai_countdown_timer.setInterval(250)
        self._ai_countdown_timer.timeout.connect(self._tick_ai_countdown)

        self._turn_elapsed_seconds = 0
        self._turn_timer = QTimer(self)
        self._turn_timer.setInterval(1000)
        self._turn_timer.timeout.connect(self._tick_turn_timer)

        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI 构建
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
        # 棋盘占 4 份，面板占 1 份，即面板约为总宽度的 20%
        layout.addWidget(self._board, 4)

        self._panel = ControlPanel()
        self._panel.confirm_requested.connect(self._on_confirm_requested)
        self._panel.undo_stone_requested.connect(self._on_undo_stone_requested)
        self._panel.undo_turn_requested.connect(self._on_undo_turn_requested)
        self._panel.save_manual_requested.connect(self._on_save_manual_requested)
        self._panel.go_home_requested.connect(self.go_home)
        layout.addWidget(self._panel, 1)

    # ------------------------------------------------------------------ #
    # 公共 API（由 AppWindow 调用）
    # ------------------------------------------------------------------ #

    def start_game(self, config: GameConfig) -> None:
        """使用给定配置初始化或重新初始化游戏。"""
        self._ai_timer.stop()
        self._turn_timer.stop()
        self._ai_countdown_timer.stop()
        self._ai_request_id += 1
        self._pending_ai_color = None
        self._active_ai_color = None
        self._active_ai_started_at = None

        ai: Dict[int, BaseAI] = {}
        if config.black_type == PlayerType.AI:
            ai[BLACK] = _make_ai(config)
        if config.white_type == PlayerType.AI:
            ai[WHITE] = _make_ai(config)
        self._finish_start_game(config, ai)

    def _finish_start_game(self, config: GameConfig, ai: Dict[int, BaseAI]) -> None:
        """AI 实例准备好后完成游戏设置。"""
        self._ai = ai
        budget_seconds = max(0.0, float(config.ai_think_time_seconds))
        self._ai_time_remaining = {
            color: budget_seconds
            for color in ai
        }

        # 创建 GameManager 并连接回调
        self._manager = GameManager(config)
        self._manager.on_stone_placed    = self._cb_stone_placed
        self._manager.on_turn_changed    = self._cb_turn_changed
        self._manager.on_game_over       = self._cb_game_over
        self._manager.on_undo            = self._cb_undo
        self._manager.on_request_ai_move = self._cb_request_ai_move
        self._manager.on_confirm_needed  = self._cb_confirm_needed
        self._manager.on_stone_removed   = self._cb_stone_removed

        # 重置 UI
        self._board.set_board(self._manager.board)
        self._board.clear_winning_line()
        self._board.set_interactive(False)
        self._panel.reset_for_new_game()
        self._panel.set_player_names(config.black_name, config.white_name)

        self._manager.start()

    def _reset_turn_timer(self, start: bool = True) -> None:
        self._turn_elapsed_seconds = 0
        self._panel.update_turn_timer(self._turn_elapsed_seconds)
        if start:
            self._turn_timer.start()
        else:
            self._turn_timer.stop()

    def _tick_turn_timer(self) -> None:
        if self._manager is None or self._manager.state == GameState.GAME_OVER:
            self._turn_timer.stop()
            return
        self._turn_elapsed_seconds += 1
        self._panel.update_turn_timer(self._turn_elapsed_seconds)

    def _ensure_ai_budget(self, color: int, ai: BaseAI) -> float:
        if color not in self._ai_time_remaining:
            manager_config = getattr(self._manager, "config", None)
            config_budget = (
                getattr(manager_config, "ai_think_time_seconds", 15 * 60)
            )
            self._ai_time_remaining[color] = max(
                0.0,
                float(getattr(ai, "total_think_time_seconds", config_budget)),
            )
        return self._ai_time_remaining[color]

    def _current_ai_time_remaining(self, color: int) -> float:
        remaining = self._ai_time_remaining.get(color, 0.0)
        if self._active_ai_color == color and self._active_ai_started_at is not None:
            remaining -= time.monotonic() - self._active_ai_started_at
        return max(0.0, remaining)

    def _ai_move_time_budget(self, color: int) -> float:
        remaining = self._current_ai_time_remaining(color)
        if remaining <= 0:
            return 0.0
        if self._manager is None:
            return remaining
        empty_count = len(self._manager.board.get_all_empty())
        stones_this_turn = self._manager.stones_needed_this_turn
        return allocate_ai_move_time(
            remaining_seconds=remaining,
            empty_count=empty_count,
            stones_this_turn=stones_this_turn,
            urgency=self._ai_position_urgency(color, empty_count),
        )

    def _ai_position_urgency(self, color: int, empty_count: int) -> float:
        ai = self._ai.get(color)
        estimator = getattr(ai, "estimate_urgency", None)
        if callable(estimator) and self._manager is not None:
            return float(
                estimator(
                    self._manager.board.copy(),
                    color,
                    self._manager.stones_needed_this_turn,
                )
            )
        if empty_count <= 80:
            return 2.0
        if empty_count <= 160:
            return 1.5
        return 1.0

    def _begin_ai_clock(self, color: int) -> None:
        self._active_ai_color = color
        self._active_ai_started_at = time.monotonic()
        self._panel.update_ai_time_remaining(self._current_ai_time_remaining(color))
        self._ai_countdown_timer.start()

    def _finish_ai_clock(self, color: int) -> float:
        remaining = self._current_ai_time_remaining(color)
        self._ai_time_remaining[color] = remaining
        if self._active_ai_color == color:
            self._active_ai_color = None
            self._active_ai_started_at = None
            self._ai_countdown_timer.stop()
        self._panel.update_ai_time_remaining(remaining)
        return remaining

    def _cancel_ai_clock(self) -> None:
        self._active_ai_color = None
        self._active_ai_started_at = None
        self._ai_countdown_timer.stop()

    def _tick_ai_countdown(self) -> None:
        if self._active_ai_color is None:
            self._ai_countdown_timer.stop()
            return
        remaining = self._current_ai_time_remaining(self._active_ai_color)
        self._panel.update_ai_time_remaining(remaining)
        if remaining <= 0:
            self._expire_ai_time_as_draw(self._active_ai_color)

    def _expire_ai_time_as_draw(self, color: int) -> None:
        self._ai_time_remaining[color] = 0.0
        self._cancel_ai_clock()
        self._ai_timer.stop()
        self._pending_ai_color = None
        self._ai_request_id += 1
        self._panel.update_ai_time_remaining(0)
        if self._manager is not None:
            self._manager.declare_draw()

    # ------------------------------------------------------------------ #
    # UI 信号处理
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
        """移除当前回合最后放置的一枚棋子。"""
        if self._manager is None:
            return
        # 仅在人类玩家回合允许撤回单子
        if self._manager.current_player.player_type != PlayerType.HUMAN:
            return
        if self._manager.undo_last_stone():
            # 隐藏确认按钮（它之前可能可见）
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
        """回退一个完整回合。"""
        if self._manager is None:
            return
        # 取消尚未执行的 AI 落子
        self._ai_timer.stop()
        self._cancel_ai_clock()
        self._ai_request_id += 1
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
            self._manager.config.black_name,
            self._manager.config.white_name,
            self._manager.winner,
        )
        filepath = os.path.join(chess_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(build_chess_manual_record(history, self._manager.winner))
        print(f"[GamePage] 棋谱已保存: {filepath}")

    # ------------------------------------------------------------------ #
    # GameManager 回调
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
        """人类玩家已落满本回合棋子，显示确认按钮。"""
        self._board.set_interactive(False)   # 确认前不再接受左键落子
        self._panel.show_confirm_button(True)
        self._panel.update_stones_placed(
            self._manager.stones_needed_this_turn,
            self._manager.stones_needed_this_turn,
        )

    def _cb_stone_removed(self, move: Move) -> None:
        """通过 undo_last_stone 撤回了一枚棋子。"""
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

        # 更新 AI 信息显示
        if color in self._ai:
            self._panel.set_ai_info(self._ai[color].name)
            self._turn_timer.stop()
            self._panel.update_ai_time_remaining(
                self._current_ai_time_remaining(color)
            )
        else:
            self._panel.set_ai_info("")
            self._cancel_ai_clock()
            self._reset_turn_timer(start=True)

        # 此处不要清除高亮；保留上一回合棋子的高亮，
        # 直到新回合第一枚棋子落下。

    def _cb_game_over(
        self, winner: Optional[int], line: List[Tuple[int, int]]
    ) -> None:
        self._ai_request_id += 1
        self._turn_timer.stop()
        self._cancel_ai_clock()
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
            self._reset_turn_timer(start=True)
        self._update_current_turn_highlight()

    def _update_current_turn_highlight(self) -> None:
        cells = [(m.row, m.col) for m in self._manager.pending_moves] \
                if self._manager else []
        self._board.set_current_turn_stones(cells)

    def _cb_request_ai_move(self, color: int) -> None:
        ai = self._ai.get(color)
        if ai is not None and self._ensure_ai_budget(color, ai) <= 0:
            self._expire_ai_time_as_draw(color)
            return
        self._pending_ai_color = color
        self._ai_timer.start(440)

    # ------------------------------------------------------------------ #
    # AI 执行
    # ------------------------------------------------------------------ #

    def _execute_ai_move(self) -> None:
        if self._manager is None or self._pending_ai_color is None:
            return
        color = self._pending_ai_color
        ai = self._ai.get(color)
        if ai is None:
            return
        remaining_budget = self._ensure_ai_budget(color, ai)
        if remaining_budget <= 0:
            self._pending_ai_color = None
            self._expire_ai_time_as_draw(color)
            return
        ai.think_time_seconds = self._ai_move_time_budget(color)

        count = self._manager.stones_needed_this_turn
        board = self._manager.board.copy()
        self._pending_ai_color = None
        self._ai_request_id += 1
        request_id = self._ai_request_id
        self._begin_ai_clock(color)

        thread = QThread(self)
        worker = _AiMoveWorker(request_id, ai, board, color, count)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_ai_moves_ready)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self._forget_ai_thread(thread))
        worker.finished.connect(lambda *_args, worker=worker: self._forget_ai_worker(worker))

        self._ai_threads.append(thread)
        self._ai_workers.append(worker)
        thread.start()

    @pyqtSlot(int, int, object)
    def _on_ai_moves_ready(self, request_id: int, color: int, moves) -> None:
        if request_id != self._ai_request_id:
            return
        if self._finish_ai_clock(color) <= 0:
            self._expire_ai_time_as_draw(color)
            return
        if self._manager is None or self._manager.state != GameState.WAITING:
            return
        if self._manager.current_color != color:
            return
        for move in moves:
            self._manager.try_place(move.row, move.col)
            if self._manager.state == GameState.GAME_OVER:
                break

    def _forget_ai_thread(self, thread: QThread) -> None:
        if thread in self._ai_threads:
            self._ai_threads.remove(thread)

    def _forget_ai_worker(self, worker: _AiMoveWorker) -> None:
        if worker in self._ai_workers:
            self._ai_workers.remove(worker)
