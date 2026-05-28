"""
Abstract AI interface for Connect6.

All AI implementations must subclass BaseAI and implement ``get_moves``.
The host (MainWindow) calls ``get_moves`` off the GUI thread when it's the
AI's turn, then feeds the returned moves to GameManager via ``try_place``.
"""

from abc import ABC, abstractmethod
from typing import List

from game.board import Board
from models.move import Move


class BaseAI(ABC):
    """Abstract base class for all Connect6 AI engines."""

    @abstractmethod
    def get_moves(self, board: Board, color: int, count: int) -> List[Move]:
        """
        Calculate the best move(s) for the current board position.

        Args:
            board:  A *snapshot* of the current board.  Do NOT modify it.
            color:  The stone color this AI controls (BLACK or WHITE).
            count:  Number of stones to place this turn (1 on the very first
                    move of the game, 2 on every subsequent turn).

        Returns:
            A list of exactly ``count`` Move objects on distinct empty cells.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable AI name shown in the UI."""
        return self.__class__.__name__
