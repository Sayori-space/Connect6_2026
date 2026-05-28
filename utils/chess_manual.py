import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from models.move import Move
from utils.constants import BLACK, WHITE


_INVALID_FILENAME_CHARS = '<>:"/\\|?*'
DEFAULT_BLACK_EXPORT_NAME = "参赛队A"
DEFAULT_WHITE_EXPORT_NAME = "参赛队B"


def _sanitize_filename_part(value: str) -> str:
    sanitized = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch for ch in value)
    sanitized = sanitized.strip().rstrip(".")
    return sanitized or "未命名"


def build_chess_manual_filename(
    manual_dir: os.PathLike[str] | str,
    black_name: str,
    white_name: str,
    winner: Optional[int],
) -> str:
    """Build a competition-style chess manual filename with a unique suffix."""
    black = _sanitize_filename_part(black_name)
    white = _sanitize_filename_part(white_name)
    base_name = f"C6-{black} vs{white}-{_result_label(winner)}"
    directory = Path(manual_dir)

    index = 1
    while True:
        filename = f"{base_name} ({index}).txt"
        if not (directory / filename).exists():
            return filename
        index += 1


def _result_label(winner: Optional[int]) -> str:
    if winner == BLACK:
        return "先手胜"
    if winner == WHITE:
        return "后手胜"
    return "和棋"


def _move_to_record_token(move: Move) -> str:
    color = "B" if move.color == BLACK else "W"
    column = chr(ord("A") + move.col)
    row = move.row + 1
    return f"{color}({column},{row})"


def build_chess_manual_record(
    moves: Iterable[Move],
    winner: Optional[int],
    recorded_at: Optional[datetime] = None,
) -> str:
    """Build the compact C6 competition record body."""
    timestamp = (recorded_at or datetime.now()).strftime("%Y-%m-%d %H:%M ")
    header = f"{{[C6][][][{_result_label(winner)}][{timestamp}][]"
    tokens = [_move_to_record_token(move) for move in moves]
    if tokens:
        return header + ";" + ";".join(tokens) + "}"
    return header + "}"
