from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    """单次落子的不可变记录。"""
    row: int
    col: int
    color: int  # BLACK 或 WHITE，见 utils.constants
