"""Run bounded AI-vs-AI self-play matches."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import csv
import io
import json
import os
import sys
import time
from typing import Dict, List, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.base_ai import BaseAI
from ai.factory import build_ai
from ai.time_control import allocate_ai_move_time
from game.game_manager import GameManager, GameState
from models.game_config import GameConfig
from models.player import PlayerType
from utils.constants import BLACK, WHITE


@dataclass(frozen=True)
class SelfPlayMatchResult:
    black_engine: str
    white_engine: str
    winner: Optional[int]
    timeout_color: Optional[int]
    turns_completed: int
    stones_played: int
    elapsed_seconds: float
    black_remaining_seconds: Optional[float] = None
    white_remaining_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "black_engine": self.black_engine,
            "white_engine": self.white_engine,
            "winner": self.winner,
            "timeout_color": self.timeout_color,
            "turns_completed": self.turns_completed,
            "stones_played": self.stones_played,
            "elapsed_seconds": self.elapsed_seconds,
            "black_remaining_seconds": self.black_remaining_seconds,
            "white_remaining_seconds": self.white_remaining_seconds,
        }


@dataclass(frozen=True)
class SelfPlaySeriesSummary:
    black_engine: str
    white_engine: str
    games: int
    black_wins: int
    white_wins: int
    draws: int
    avg_turns_completed: float
    avg_elapsed_seconds: float
    results: List[SelfPlayMatchResult]

    def to_dict(self) -> dict:
        return {
            "black_engine": self.black_engine,
            "white_engine": self.white_engine,
            "games": self.games,
            "black_wins": self.black_wins,
            "white_wins": self.white_wins,
            "draws": self.draws,
            "avg_turns_completed": self.avg_turns_completed,
            "avg_elapsed_seconds": self.avg_elapsed_seconds,
            "results": [result.to_dict() for result in self.results],
        }

    def to_csv(self) -> str:
        return _results_to_csv(self.results)


@dataclass(frozen=True)
class PairedSelfPlaySummary:
    engine_a: str
    engine_b: str
    games: int
    engine_a_wins: int
    engine_b_wins: int
    draws: int
    avg_turns_completed: float
    avg_elapsed_seconds: float
    results: List[SelfPlayMatchResult]

    def to_dict(self) -> dict:
        return {
            "engine_a": self.engine_a,
            "engine_b": self.engine_b,
            "games": self.games,
            "engine_a_wins": self.engine_a_wins,
            "engine_b_wins": self.engine_b_wins,
            "draws": self.draws,
            "avg_turns_completed": self.avg_turns_completed,
            "avg_elapsed_seconds": self.avg_elapsed_seconds,
            "results": [result.to_dict() for result in self.results],
        }

    def to_csv(self) -> str:
        return _results_to_csv(self.results)


def _results_to_csv(results: List[SelfPlayMatchResult]) -> str:
    handle = io.StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(
        [
            "game",
            "black_engine",
            "white_engine",
            "winner",
            "timeout_color",
            "turns_completed",
            "stones_played",
            "elapsed_seconds",
            "black_remaining_seconds",
            "white_remaining_seconds",
        ]
    )
    for index, result in enumerate(results, start=1):
        writer.writerow(
            [
                index,
                result.black_engine,
                result.white_engine,
                "" if result.winner is None else result.winner,
                "" if result.timeout_color is None else result.timeout_color,
                result.turns_completed,
                result.stones_played,
                f"{result.elapsed_seconds:.6f}",
                (
                    ""
                    if result.black_remaining_seconds is None
                    else f"{result.black_remaining_seconds:.6f}"
                ),
                (
                    ""
                    if result.white_remaining_seconds is None
                    else f"{result.white_remaining_seconds:.6f}"
                ),
            ]
        )
    return handle.getvalue()


def _build_engine(engine: str, move_time_seconds: float) -> BaseAI:
    ai = build_ai(GameConfig(ai_type=engine))
    ai.think_time_seconds = move_time_seconds
    return ai


def _place_fallback_stones(manager: GameManager, color: int, needed: int) -> None:
    for row, col in manager.board.get_all_empty():
        if manager.current_color != color or manager.state != GameState.WAITING:
            return
        before = len(manager.board.history)
        manager.try_place(row, col)
        if len(manager.board.history) > before:
            needed -= 1
        if needed <= 0:
            return


def _estimate_urgency(
    ai: BaseAI,
    manager: GameManager,
    color: int,
    needed: int,
) -> float:
    estimator = getattr(ai, "estimate_urgency", None)
    if callable(estimator):
        return float(estimator(manager.board.copy(), color, needed))
    empty_count = len(manager.board.get_all_empty())
    if empty_count <= 80:
        return 2.0
    if empty_count <= 160:
        return 1.5
    return 1.0


def run_self_play_match(
    black_engine: str,
    white_engine: str,
    max_turns: int = 200,
    move_time_seconds: float = 0.05,
    total_time_seconds: Optional[float] = None,
) -> SelfPlayMatchResult:
    config = GameConfig(
        black_type=PlayerType.AI,
        white_type=PlayerType.AI,
        black_name=black_engine,
        white_name=white_engine,
    )
    manager = GameManager(config)
    engines: Dict[int, BaseAI] = {
        BLACK: _build_engine(black_engine, move_time_seconds),
        WHITE: _build_engine(white_engine, move_time_seconds),
    }

    started = time.monotonic()
    manager.start()
    turns_completed = 0
    timeout_color: Optional[int] = None
    remaining = (
        {
            BLACK: max(0.0, float(total_time_seconds)),
            WHITE: max(0.0, float(total_time_seconds)),
        }
        if total_time_seconds is not None
        else None
    )

    while manager.state == GameState.WAITING and turns_completed < max_turns:
        color = manager.current_color
        needed = manager.stones_needed_this_turn
        ai = engines[color]

        if remaining is not None:
            if remaining[color] <= 0:
                timeout_color = color
                manager.declare_draw()
                break
            ai.think_time_seconds = allocate_ai_move_time(
                remaining_seconds=remaining[color],
                empty_count=len(manager.board.get_all_empty()),
                stones_this_turn=needed,
                urgency=_estimate_urgency(ai, manager, color, needed),
            )
        else:
            ai.think_time_seconds = move_time_seconds

        search_started = time.monotonic()
        moves = ai.get_moves(manager.board.copy(), color, needed)
        search_elapsed = time.monotonic() - search_started
        if remaining is not None:
            remaining[color] = max(0.0, remaining[color] - search_elapsed)
            if remaining[color] <= 0:
                timeout_color = color
                manager.declare_draw()
                break

        placed = 0
        for move in moves:
            if manager.current_color != color or manager.state != GameState.WAITING:
                break
            before = len(manager.board.history)
            manager.try_place(move.row, move.col)
            if len(manager.board.history) > before:
                placed += 1
            if placed >= needed:
                break

        if manager.current_color == color and manager.state == GameState.WAITING:
            _place_fallback_stones(manager, color, needed - placed)

        turns_completed += 1

    elapsed = time.monotonic() - started
    return SelfPlayMatchResult(
        black_engine=black_engine,
        white_engine=white_engine,
        winner=manager.winner,
        timeout_color=timeout_color,
        turns_completed=turns_completed,
        stones_played=len(manager.board.history),
        elapsed_seconds=elapsed,
        black_remaining_seconds=remaining[BLACK] if remaining is not None else None,
        white_remaining_seconds=remaining[WHITE] if remaining is not None else None,
    )


def run_self_play_series(
    black_engine: str,
    white_engine: str,
    games: int = 20,
    max_turns: int = 200,
    move_time_seconds: float = 0.05,
    total_time_seconds: Optional[float] = None,
) -> SelfPlaySeriesSummary:
    results = [
        run_self_play_match(
            black_engine=black_engine,
            white_engine=white_engine,
            max_turns=max_turns,
            move_time_seconds=move_time_seconds,
            total_time_seconds=total_time_seconds,
        )
        for _ in range(games)
    ]
    black_wins = sum(1 for result in results if result.winner == BLACK)
    white_wins = sum(1 for result in results if result.winner == WHITE)
    draws = sum(1 for result in results if result.winner is None)
    return SelfPlaySeriesSummary(
        black_engine=black_engine,
        white_engine=white_engine,
        games=games,
        black_wins=black_wins,
        white_wins=white_wins,
        draws=draws,
        avg_turns_completed=(
            sum(result.turns_completed for result in results) / games
            if games
            else 0.0
        ),
        avg_elapsed_seconds=(
            sum(result.elapsed_seconds for result in results) / games
            if games
            else 0.0
        ),
        results=results,
    )


def run_paired_self_play_series(
    engine_a: str,
    engine_b: str,
    pairs: int = 10,
    max_turns: int = 200,
    move_time_seconds: float = 0.05,
    total_time_seconds: Optional[float] = None,
) -> PairedSelfPlaySummary:
    results: List[SelfPlayMatchResult] = []
    for _ in range(pairs):
        results.append(
            run_self_play_match(
                black_engine=engine_a,
                white_engine=engine_b,
                max_turns=max_turns,
                move_time_seconds=move_time_seconds,
                total_time_seconds=total_time_seconds,
            )
        )
        results.append(
            run_self_play_match(
                black_engine=engine_b,
                white_engine=engine_a,
                max_turns=max_turns,
                move_time_seconds=move_time_seconds,
                total_time_seconds=total_time_seconds,
            )
        )

    engine_a_wins = 0
    engine_b_wins = 0
    draws = 0
    for result in results:
        if result.winner is None:
            draws += 1
            continue
        winning_engine = (
            result.black_engine if result.winner == BLACK else result.white_engine
        )
        if winning_engine == engine_a:
            engine_a_wins += 1
        elif winning_engine == engine_b:
            engine_b_wins += 1

    games = len(results)
    return PairedSelfPlaySummary(
        engine_a=engine_a,
        engine_b=engine_b,
        games=games,
        engine_a_wins=engine_a_wins,
        engine_b_wins=engine_b_wins,
        draws=draws,
        avg_turns_completed=(
            sum(result.turns_completed for result in results) / games
            if games
            else 0.0
        ),
        avg_elapsed_seconds=(
            sum(result.elapsed_seconds for result in results) / games
            if games
            else 0.0
        ),
        results=results,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--black", default="alpha_belta_max")
    parser.add_argument("--white", default="alpha_belta_plus")
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--paired", action="store_true")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("--move-time", type=float, default=0.05)
    parser.add_argument("--total-time", type=float, default=None)
    args = parser.parse_args()

    if args.paired:
        summary = run_paired_self_play_series(
            engine_a=args.black,
            engine_b=args.white,
            pairs=args.games,
            max_turns=args.max_turns,
            move_time_seconds=args.move_time,
            total_time_seconds=args.total_time,
        )
    else:
        summary = run_self_play_series(
            black_engine=args.black,
            white_engine=args.white,
            games=args.games,
            max_turns=args.max_turns,
            move_time_seconds=args.move_time,
            total_time_seconds=args.total_time,
        )

    if args.format == "csv":
        print(summary.to_csv(), end="")
    else:
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
