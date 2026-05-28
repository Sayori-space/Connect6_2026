"""
RandomAI – placeholder AI that places stones at random.

Useful for smoke-testing the game loop and UI before a real engine is added.
Replace this class (or add a new BaseAI subclass) to implement smarter play.
"""

import random
from typing import List

from ai.base_ai import BaseAI
from game.board import Board
from models.move import Move


class RandomAI(BaseAI):
    """Picks empty intersections uniformly at random."""

    def get_moves(self, board: Board, color: int, count: int) -> List[Move]:
        empty = board.get_all_empty()
        count = min(count, len(empty))
        chosen = random.sample(empty, count)
        return [Move(r, c, color) for r, c in chosen]

    @property
    def name(self) -> str:
        return "随机AI"
