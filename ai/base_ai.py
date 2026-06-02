"""
六子棋 AI 抽象接口。

所有 AI 实现都必须继承 BaseAI 并实现 ``get_moves``。
当轮到 AI 落子时，宿主（MainWindow）会在 GUI 线程外调用 ``get_moves``，
再通过 ``try_place`` 将返回的落子交给 GameManager。
"""

from abc import ABC, abstractmethod
from typing import List

from game.board import Board
from models.move import Move


class BaseAI(ABC):
    """所有六子棋 AI 引擎的抽象基类。"""

    @abstractmethod
    def get_moves(self, board: Board, color: int, count: int) -> List[Move]:
        """
        计算当前局面下的最佳落子。

        参数：
            board: 当前棋盘的 *快照*。不要修改它。
            color: 该 AI 控制的棋子颜色（BLACK 或 WHITE）。
            count: 本回合需要落下的棋子数（全局第一手为 1，之后每回合为 2）。

        返回：
            长度正好为 ``count`` 的 Move 列表，且都落在不同空位上。
        """
        ...

    @property
    def name(self) -> str:
        """显示在 UI 中的可读 AI 名称。"""
        return self.__class__.__name__
