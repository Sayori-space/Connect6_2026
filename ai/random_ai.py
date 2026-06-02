"""
RandomAI：随机落子的占位 AI。

在真正引擎接入前，可用于对游戏循环和 UI 做冒烟测试。
替换此类（或新增 BaseAI 子类）即可实现更智能的走法。
"""

import random
from typing import List

from ai.base_ai import BaseAI
from game.board import Board
from models.move import Move


class RandomAI(BaseAI):
    """在空交叉点中均匀随机选择落子。"""

    def get_moves(self, board: Board, color: int, count: int) -> List[Move]:
        empty = board.get_all_empty()
        count = min(count, len(empty))
        chosen = random.sample(empty, count)
        return [Move(r, c, color) for r, c in chosen]

    @property
    def name(self) -> str:
        return "随机AI"
