"""Utilities for evaluating AI engines on fixed Connect6 positions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Iterable, List, Set, Tuple

from ai.base_ai import BaseAI
from game.board import Board
from models.move import Move


Cell = Tuple[int, int]


@dataclass(frozen=True)
class AIPosition:
    position_id: str
    description: str
    board_size: int
    moves: Tuple[Tuple[int, int, int], ...]
    color: int
    count: int
    recommended_cells: Set[Cell]
    recommended_groups: Tuple[frozenset[Cell], ...]
    forbidden_cells: Set[Cell]
    max_seconds: float

    def build_board(self) -> Board:
        board = Board(self.board_size)
        for row, col, color in self.moves:
            if not board.place(Move(row, col, color)):
                raise ValueError(
                    f"invalid move in fixture {self.position_id}: "
                    f"({row}, {col}, {color})"
                )
        return board


@dataclass(frozen=True)
class AIPositionResult:
    position_id: str
    passed: bool
    selected_cells: Set[Cell]
    elapsed_seconds: float
    reason: str
    decision_reason: str
    search_nodes: int
    completed_depth: int


def _cells(raw_cells: Iterable[Iterable[int]]) -> Set[Cell]:
    return {(int(row), int(col)) for row, col in raw_cells}


def _cell_groups(raw_groups: Iterable[Iterable[Iterable[int]]]) -> Tuple[frozenset[Cell], ...]:
    return tuple(frozenset(_cells(group)) for group in raw_groups)


def load_position_fixture(path: str) -> AIPosition:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return AIPosition(
        position_id=str(payload["id"]),
        description=str(payload.get("description", "")),
        board_size=int(payload.get("board_size", 19)),
        moves=tuple(
            (int(row), int(col), int(color))
            for row, col, color in payload.get("moves", [])
        ),
        color=int(payload["color"]),
        count=int(payload["count"]),
        recommended_cells=_cells(payload.get("recommended_cells", [])),
        recommended_groups=_cell_groups(payload.get("recommended_groups", [])),
        forbidden_cells=_cells(payload.get("forbidden_cells", [])),
        max_seconds=float(payload.get("max_seconds", 1.0)),
    )


def load_position_fixtures(directory: str) -> List[AIPosition]:
    positions: List[AIPosition] = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            positions.append(load_position_fixture(os.path.join(directory, name)))
    return positions


def evaluate_position(position: AIPosition, ai: BaseAI) -> AIPositionResult:
    board = position.build_board()
    start = time.monotonic()
    moves = ai.get_moves(board, position.color, position.count)
    elapsed = time.monotonic() - start
    selected = {(move.row, move.col) for move in moves}
    decision = getattr(ai, "last_decision", {})
    stats = getattr(ai, "last_search_stats", {})

    missing_recommended = position.recommended_cells - selected
    missing_groups = [
        group
        for group in position.recommended_groups
        if not group.intersection(selected)
    ]
    forbidden_selected = position.forbidden_cells.intersection(selected)
    passed = (
        not missing_recommended
        and not missing_groups
        and not forbidden_selected
        and elapsed <= position.max_seconds
    )

    if missing_recommended:
        reason = f"missing recommended cells: {sorted(missing_recommended)}"
    elif missing_groups:
        reason = f"missing recommended groups: {[sorted(group) for group in missing_groups]}"
    elif forbidden_selected:
        reason = f"selected forbidden cells: {sorted(forbidden_selected)}"
    elif elapsed > position.max_seconds:
        reason = (
            f"elapsed {elapsed:.3f}s exceeds limit "
            f"{position.max_seconds:.3f}s"
        )
    else:
        reason = "passed"

    return AIPositionResult(
        position_id=position.position_id,
        passed=passed,
        selected_cells=selected,
        elapsed_seconds=elapsed,
        reason=reason,
        decision_reason=str(decision.get("reason", "")),
        search_nodes=int(stats.get("nodes", 0)),
        completed_depth=int(stats.get("completed_depth", 0)),
    )
