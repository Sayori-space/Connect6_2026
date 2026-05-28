"""
Connect6 rule definitions.

All functions are pure – they receive board data and return results
without modifying any state.
"""

from typing import List, Tuple
from models.move import Move

WIN_LENGTH = 6

# (delta-row, delta-col) for each of the four line directions
DIRECTIONS: List[Tuple[int, int]] = [(0, 1), (1, 0), (1, 1), (1, -1)]


def check_win(board, last_move: Move) -> Tuple[bool, List[Tuple[int, int]]]:
    """
    Test whether *last_move* completes a winning six-in-a-row.

    Returns:
        (True, winning_positions)  if the move wins the game
        (False, [])                otherwise
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
    """Collect all consecutive same-color stones in both directions along (dr, dc)."""
    positions: List[Tuple[int, int]] = [(row, col)]

    # Forward
    r, c = row + dr, col + dc
    while board.is_valid_position(r, c) and board.get(r, c) == color:
        positions.append((r, c))
        r += dr
        c += dc

    # Backward
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
    How many stones the current player must place.

    Black places exactly 1 stone on turn 1 (the very first move of the game).
    Every subsequent turn, both players place exactly 2 stones.

    Args:
        move_number: 1-indexed global move counter.
    """
    return 1 if move_number == 1 else 2
