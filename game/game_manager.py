"""
GameManager：游戏流程的核心控制器。

职责：
  * 持有 Board，并跟踪当前轮到哪一方。
  * 校验并记录落子。
  * 检测胜负和平局条件。
  * 提供清晰的回调 API，让 UI、AI 和测试都能观察游戏事件，同时避免循环导入。

本模块不依赖 PyQt5 或任何 UI 代码。
"""

from typing import Callable, Dict, List, Optional, Tuple

from game.board import Board
from game.rules import check_win, is_board_full, stones_per_turn
from models.game_config import GameConfig
from models.move import Move
from models.player import Player, PlayerType
from utils.constants import BLACK, WHITE


class GameState:
    WAITING          = "waiting"        # 等待当前玩家输入
    AWAITING_CONFIRM = "confirm"        # 人类玩家已落满棋子，等待确认
    GAME_OVER        = "game_over"      # 游戏已结束


class GameManager:
    """
    纯逻辑游戏控制器。

    只通过 ``on_*`` 回调与外部通信。
    请在调用 :py:meth:`start` 前设置这些回调。
    """

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    def __init__(self, config: GameConfig):
        self.config = config
        self.board = Board(config.board_size)

        self.players: Dict[int, Player] = {
            BLACK: Player(BLACK, config.black_type, config.black_name),
            WHITE: Player(WHITE, config.white_type, config.white_name),
        }

        self._state: str = GameState.WAITING
        self._current_color: int = BLACK
        self._move_number: int = 1          # 从 1 开始计数；每完成一回合递增
        self._stones_this_turn: int = 0     # 当前回合已落棋子数
        self._stones_needed: int = stones_per_turn(1)
        self._pending_moves: List[Move] = []
        self._turn_history: List[int] = []  # 每个已完成回合的棋子数

        self._winner: Optional[int] = None
        self._winning_line: List[Tuple[int, int]] = []

        # --- 回调（由宿主设置，例如 GamePage） ---
        # 每次成功落子后调用
        self.on_stone_placed: Optional[Callable[[Move], None]] = None
        # 当前玩家或所需落子数变化时调用
        self.on_turn_changed: Optional[Callable[[int, int], None]] = None
        # 游戏结束时调用；winner 为 None 表示平局
        self.on_game_over: Optional[Callable[[Optional[int], List[Tuple[int, int]]], None]] = None
        # undo() 后调用；接收被移除的落子列表
        self.on_undo: Optional[Callable[[List[Move]], None]] = None
        # 当前玩家是 AI 且需要落子时调用
        self.on_request_ai_move: Optional[Callable[[int], None]] = None
        # 人类玩家已落满本回合棋子且需要确认时调用
        self.on_confirm_needed: Optional[Callable[[], None]] = None
        # undo_last_stone() 后调用；接收被移除的落子
        self.on_stone_removed: Optional[Callable[[Move], None]] = None

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def current_color(self) -> int:
        return self._current_color

    @property
    def current_player(self) -> Player:
        return self.players[self._current_color]

    @property
    def state(self) -> str:
        return self._state

    @property
    def winner(self) -> Optional[int]:
        return self._winner

    @property
    def winning_line(self) -> List[Tuple[int, int]]:
        return list(self._winning_line)

    @property
    def stones_placed_this_turn(self) -> int:
        return self._stones_this_turn

    @property
    def stones_needed_this_turn(self) -> int:
        return self._stones_needed

    @property
    def turn_history(self) -> List[int]:
        """每个已完成 GameManager 回合的棋子数（1, 2, 2, 2, ...）。"""
        return list(self._turn_history)

    @property
    def pending_moves(self) -> List[Move]:
        """当前回合中已落下但尚未确认或推进的棋子。"""
        return list(self._pending_moves)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def start(self):
        """开始游戏，或在重置后重新开始。"""
        self._state = GameState.WAITING
        self._notify_turn()
        self._maybe_trigger_ai()

    def try_place(self, row: int, col: int) -> bool:
        """
        尝试为当前玩家在 (row, col) 处落子。

        对人类玩家来说，本回合所需棋子落满后可能进入 AWAITING_CONFIRM。
        调用 confirm_turn() 才会最终结束该回合。

        落子被接受时返回 True。
        """
        if self._state != GameState.WAITING:
            return False
        if not self.board.is_empty(row, col):
            return False

        move = Move(row, col, self._current_color)
        self.board.place(move)
        self._pending_moves.append(move)
        self._stones_this_turn += 1

        if self.on_stone_placed:
            self.on_stone_placed(move)

        # 每次落子后都检查是否获胜
        won, line = check_win(self.board, move)
        if won:
            self._end_game(self._current_color, line)
            return True

        if self._stones_this_turn >= self._stones_needed:
            if self.current_player.player_type == PlayerType.HUMAN:
                # 等待人类玩家显式确认
                self._state = GameState.AWAITING_CONFIRM
                if self.on_confirm_needed:
                    self.on_confirm_needed()
            else:
                self._advance_turn()

        return True

    def confirm_turn(self) -> bool:
        """
        人类玩家确认本回合落子并结束回合。

        仅在 AWAITING_CONFIRM 状态下有效。成功返回 True。
        """
        if self._state != GameState.AWAITING_CONFIRM:
            return False
        self._state = GameState.WAITING
        self._advance_turn()
        return True

    def undo_last_stone(self) -> bool:
        """
        移除 *当前* 回合中最近放置的一枚棋子。

        在落子中（WAITING）和已落满待确认（AWAITING_CONFIRM）状态都可用。
        成功移除棋子时返回 True。
        """
        if self._state not in (GameState.WAITING, GameState.AWAITING_CONFIRM):
            return False
        if self._stones_this_turn == 0:
            return False

        # 如果处于确认状态，则回退到 WAITING
        self._state = GameState.WAITING

        m = self.board.undo()
        if m:
            self._stones_this_turn -= 1
            self._pending_moves.pop()
            if self.on_stone_removed:
                self.on_stone_removed(m)
            return True
        return False

    def undo(self) -> bool:
        """
        撤销最近一个 *完整* 回合，或清空当前未完成回合。

        * 如果当前回合已有落子（包括 AWAITING_CONFIRM），则全部移除。
        * 否则撤销上一位玩家已确认的回合。

        有内容被撤销时返回 True。
        """
        if self._state == GameState.GAME_OVER:
            return False

        undone: List[Move] = []

        if self._stones_this_turn > 0:
            # 撤销当前未完成或待确认回合
            for _ in range(self._stones_this_turn):
                m = self.board.undo()
                if m:
                    undone.append(m)
            self._stones_this_turn = 0
            self._pending_moves.clear()
            self._state = GameState.WAITING
        elif self._turn_history:
            # 撤销上一位玩家已完成的回合
            prev_count = self._turn_history.pop()
            self._current_color = WHITE if self._current_color == BLACK else BLACK
            self._move_number -= 1
            self._stones_needed = prev_count
            self._stones_this_turn = 0
            self._pending_moves.clear()
            self._state = GameState.WAITING
            for _ in range(prev_count):
                m = self.board.undo()
                if m:
                    undone.append(m)
        else:
            return False

        if undone and self.on_undo:
            self.on_undo(undone)
        self._notify_turn()
        return True

    def resign(self):
        """当前玩家认输。"""
        if self._state not in (GameState.WAITING, GameState.AWAITING_CONFIRM):
            return
        winner = WHITE if self._current_color == BLACK else BLACK
        self._end_game(winner, [])

    def declare_draw(self) -> bool:
        """Immediately end the game as a draw."""
        if self._state == GameState.GAME_OVER:
            return False
        self._end_game(None, [])
        return True

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _advance_turn(self):
        self._turn_history.append(self._stones_needed)
        self._pending_moves.clear()
        self._stones_this_turn = 0
        self._move_number += 1
        self._current_color = WHITE if self._current_color == BLACK else BLACK
        self._stones_needed = stones_per_turn(self._move_number)

        if is_board_full(self.board):
            self._end_game(None, [])
            return

        self._notify_turn()
        self._maybe_trigger_ai()

    def _end_game(self, winner: Optional[int], line: List[Tuple[int, int]]):
        self._state = GameState.GAME_OVER
        self._winner = winner
        self._winning_line = line
        if self.on_game_over:
            self.on_game_over(winner, line)

    def _notify_turn(self):
        if self.on_turn_changed:
            self.on_turn_changed(self._current_color, self._stones_needed)

    def _maybe_trigger_ai(self):
        if self._state != GameState.WAITING:
            return
        if self.current_player.player_type == PlayerType.AI:
            if self.on_request_ai_move:
                self.on_request_ai_move(self._current_color)
