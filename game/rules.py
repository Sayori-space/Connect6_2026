"""
六子棋规则定义。

所有函数都是纯函数：接收棋盘数据并返回结果，不修改任何状态。
"""

from typing import List, Tuple
from models.move import Move

WIN_LENGTH = 6

# 四个连线方向对应的 (行增量, 列增量)
DIRECTIONS: List[Tuple[int, int]] = [(0, 1), (1, 0), (1, 1), (1, -1)]


def check_win(board, last_move: Move) -> Tuple[bool, List[Tuple[int, int]]]:
    """
    检查 *last_move* 是否形成六连获胜。

    返回：
        (True, winning_positions)  表示该步获胜
        (False, [])                表示尚未获胜
    """
    color = last_move.color
    row, col = last_move.row, last_move.col

    for dr, dc in DIRECTIONS:
        line = _collect_line(board, row, col, dr, dc, color)
        if len(line) >= WIN_LENGTH:
            return True, line

    return False, []


def _collect_line(
    board, row: int, col: int, dr: int, dc: int, color: int
) -> List[Tuple[int, int]]:
    """沿 (dr, dc) 正反两个方向收集连续同色棋子。"""
    positions: List[Tuple[int, int]] = [(row, col)]

    # 正方向
    r, c = row + dr, col + dc
    while board.is_valid_position(r, c) and board.get(r, c) == color:
        positions.append((r, c))
        r += dr
        c += dc

    # 反方向
    r, c = row - dr, col - dc
    while board.is_valid_position(r, c) and board.get(r, c) == color:
        positions.insert(0, (r, c))
        r -= dr
        c -= dc

    return positions


def is_board_full(board) -> bool:
    return not board.get_all_empty()


def stones_per_turn(move_number: int) -> int:
    """
    当前玩家本回合必须落下的棋子数。

    黑方第一回合（全局第一步）只落 1 子。
    之后每个回合，双方都必须落 2 子。

    参数：
        move_number: 从 1 开始计数的全局回合编号。
    """
    return 1 if move_number == 1 else 2
