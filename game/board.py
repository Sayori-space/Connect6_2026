from typing import List, Optional, Tuple
from utils.constants import EMPTY, DEFAULT_BOARD_SIZE
from models.move import Move


class Board:
    """
    保存棋盘状态和完整落子历史。
    与 UI 和游戏流程逻辑完全解耦。
    """

    def __init__(self, size: int = DEFAULT_BOARD_SIZE):
        self.size = size
        self._grid: List[List[int]] = [[EMPTY] * size for _ in range(size)]
        self._history: List[Move] = []

    # ------------------------------------------------------------------ #
    # 状态修改
    # ------------------------------------------------------------------ #

    def place(self, move: Move) -> bool:
        """放置一枚棋子；成功返回 True，位置无效则返回 False。"""
        if not self.is_valid_position(move.row, move.col):
            return False
        if self._grid[move.row][move.col] != EMPTY:
            return False
        self._grid[move.row][move.col] = move.color
        self._history.append(move)
        return True

    def undo(self) -> Optional[Move]:
        """移除最后一枚棋子；返回被移除的 Move，或 None。"""
        if not self._history:
            return None
        move = self._history.pop()
        self._grid[move.row][move.col] = EMPTY
        return move

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, row: int, col: int) -> int:
        """返回 (row, col) 处的占用状态；越界时返回 -1。"""
        if self.is_valid_position(row, col):
            return self._grid[row][col]
        return -1

    def is_valid_position(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def is_empty(self, row: int, col: int) -> bool:
        return self.is_valid_position(row, col) and self._grid[row][col] == EMPTY

    def get_all_empty(self) -> List[Tuple[int, int]]:
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self._grid[r][c] == EMPTY
        ]

    @property
    def history(self) -> List[Move]:
        return list(self._history)

    def copy(self) -> "Board":
        new_board = Board(self.size)
        for r in range(self.size):
            for c in range(self.size):
                new_board._grid[r][c] = self._grid[r][c]
        new_board._history = list(self._history)
        return new_board
