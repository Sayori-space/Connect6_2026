"""
GameManager – central game-flow controller.

Responsibilities:
  * Owns the Board and tracks whose turn it is.
  * Validates and records moves.
  * Detects win / draw conditions.
  * Exposes a clean callback API so that UI, AI, and tests can all observe
    game events without any circular imports.

This module has ZERO dependency on PyQt5 or any UI code.
"""

from typing import Callable, Dict, List, Optional, Tuple

from game.board import Board
from game.rules import check_win, is_board_full, stones_per_turn
from models.game_config import GameConfig
from models.move import Move
from models.player import Player, PlayerType
from utils.constants import BLACK, WHITE


class GameState:
    WAITING          = "waiting"        # waiting for the current player's input
    AWAITING_CONFIRM = "confirm"        # human placed all stones; waiting for confirm
    GAME_OVER        = "game_over"      # the game has ended


class GameManager:
    """
    Pure-logic game controller.

    Communicate with the outside world exclusively via the ``on_*`` callbacks.
    Set them before calling :py:meth:`start`.
    """

    # ------------------------------------------------------------------
    # Construction
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
        self._move_number: int = 1          # 1-indexed; increments each full turn
        self._stones_this_turn: int = 0     # stones placed in the current turn
        self._stones_needed: int = stones_per_turn(1)
        self._pending_moves: List[Move] = []
        self._turn_history: List[int] = []  # stone-count of each completed turn

        self._winner: Optional[int] = None
        self._winning_line: List[Tuple[int, int]] = []

        # --- Callbacks (set by the host, e.g. GamePage) ---
        # Called after every accepted stone placement
        self.on_stone_placed: Optional[Callable[[Move], None]] = None
        # Called when the active player / stones-needed changes
        self.on_turn_changed: Optional[Callable[[int, int], None]] = None
        # Called when the game ends; winner is None for a draw
        self.on_game_over: Optional[Callable[[Optional[int], List[Tuple[int, int]]], None]] = None
        # Called after undo(); receives the list of moves that were removed
        self.on_undo: Optional[Callable[[List[Move]], None]] = None
        # Called when the current player is an AI and needs to move
        self.on_request_ai_move: Optional[Callable[[int], None]] = None
        # Called when a human has placed all required stones and must confirm
        self.on_confirm_needed: Optional[Callable[[], None]] = None
        # Called after undo_last_stone(); receives the removed move
        self.on_stone_removed: Optional[Callable[[Move], None]] = None

    # ------------------------------------------------------------------
    # Read-only properties
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
        """Stone counts for each completed GameManager turn (1, 2, 2, 2, ...)."""
        return list(self._turn_history)

    @property
    def pending_moves(self) -> List[Move]:
        """Moves placed in the current (not yet confirmed/advanced) turn."""
        return list(self._pending_moves)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Begin (or restart after reset) the game."""
        self._state = GameState.WAITING
        self._notify_turn()
        self._maybe_trigger_ai()

    def try_place(self, row: int, col: int) -> bool:
        """
        Attempt to place a stone for the current player at (row, col).

        For human players this may transition into AWAITING_CONFIRM once all
        required stones for the turn have been placed.  Call confirm_turn()
        to finalise the turn.

        Returns True if the placement was accepted.
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

        # Check for win after every stone
        won, line = check_win(self.board, move)
        if won:
            self._end_game(self._current_color, line)
            return True

        if self._stones_this_turn >= self._stones_needed:
            if self.current_player.player_type == PlayerType.HUMAN:
                # Wait for the human to explicitly confirm
                self._state = GameState.AWAITING_CONFIRM
                if self.on_confirm_needed:
                    self.on_confirm_needed()
            else:
                self._advance_turn()

        return True

    def confirm_turn(self) -> bool:
        """
        Human player confirms their stone placements and ends their turn.

        Only valid in AWAITING_CONFIRM state.  Returns True on success.
        """
        if self._state != GameState.AWAITING_CONFIRM:
            return False
        self._state = GameState.WAITING
        self._advance_turn()
        return True

    def undo_last_stone(self) -> bool:
        """
        Remove the most recently placed stone within the *current* turn.

        Works both while placing (WAITING) and after all stones are placed
        (AWAITING_CONFIRM).  Returns True if a stone was removed.
        """
        if self._state not in (GameState.WAITING, GameState.AWAITING_CONFIRM):
            return False
        if self._stones_this_turn == 0:
            return False

        # Revert to WAITING if we were in the confirm state
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
        Undo the most recent *complete* turn (or clear the current partial turn).

        * If any stones have been placed in the current turn (including
          AWAITING_CONFIRM), all of them are removed.
        * Otherwise the previous player's confirmed turn is reversed.

        Returns True if anything was undone.
        """
        if self._state == GameState.GAME_OVER:
            return False

        undone: List[Move] = []

        if self._stones_this_turn > 0:
            # Undo the current partial / awaiting-confirm turn
            for _ in range(self._stones_this_turn):
                m = self.board.undo()
                if m:
                    undone.append(m)
            self._stones_this_turn = 0
            self._pending_moves.clear()
            self._state = GameState.WAITING
        elif self._turn_history:
            # Undo the previous player's completed turn
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
        """The current player forfeits the game."""
        if self._state not in (GameState.WAITING, GameState.AWAITING_CONFIRM):
            return
        winner = WHITE if self._current_color == BLACK else BLACK
        self._end_game(winner, [])

    # ------------------------------------------------------------------
    # Private helpers
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
