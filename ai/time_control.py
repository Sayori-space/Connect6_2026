"""Shared AI time-allocation helpers."""

from __future__ import annotations

import math


MIN_AI_MOVE_BUDGET_SECONDS = 0.05


def allocate_ai_move_time(
    remaining_seconds: float,
    empty_count: int,
    stones_this_turn: int,
    urgency: float = 1.0,
    min_budget_seconds: float = MIN_AI_MOVE_BUDGET_SECONDS,
) -> float:
    """Allocate one move's search budget from a whole-game remaining clock."""
    remaining = max(0.0, float(remaining_seconds))
    if remaining <= 0:
        return 0.0

    empty_after_this_turn = max(0, int(empty_count) - int(stones_this_turn))
    future_ai_turns = 1 + math.ceil(empty_after_this_turn / 4)
    urgency = max(0.25, float(urgency))
    budget = (remaining / max(1, future_ai_turns)) * urgency

    if remaining <= min_budget_seconds:
        return remaining
    return min(remaining, max(min_budget_seconds, budget))
