from __future__ import annotations

import argparse
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import ai.alpha_beta_ai as alpha_beta_module
from ai.alpha_beta_ai import AlphaBetaAI
from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI
from game.board import Board
from game.rules import check_win, stones_per_turn
from models.move import Move
from utils.constants import BLACK, WHITE


Opening = List[Tuple[int, int, int]]


@dataclass(frozen=True)
class NamedOpening:
    name: str
    moves: Opening

OPENINGS: List[Opening] = [
    [],
    [
        (9, 9, BLACK),
        (9, 10, WHITE),
        (10, 9, WHITE),
    ],
]

OPENING_SUITE: List[NamedOpening] = [
    NamedOpening("empty", []),
    NamedOpening(
        "center_reply",
        [
            (9, 9, BLACK),
            (9, 10, WHITE),
            (10, 9, WHITE),
        ],
    ),
    NamedOpening(
        "black_one_sided_four",
        [
            (9, 4, WHITE),
            (9, 5, BLACK),
            (9, 6, BLACK),
            (9, 7, BLACK),
            (9, 8, BLACK),
        ],
    ),
    NamedOpening(
        "white_one_sided_four",
        [
            (9, 4, BLACK),
            (9, 5, WHITE),
            (9, 6, WHITE),
            (9, 7, WHITE),
            (9, 8, WHITE),
        ],
    ),
    NamedOpening(
        "black_cross_four",
        [
            (9, 5, BLACK),
            (9, 6, BLACK),
            (9, 7, BLACK),
            (9, 8, BLACK),
            (5, 9, BLACK),
            (6, 9, BLACK),
            (7, 9, BLACK),
            (8, 9, BLACK),
        ],
    ),
    NamedOpening(
        "white_cross_four",
        [
            (9, 5, WHITE),
            (9, 6, WHITE),
            (9, 7, WHITE),
            (9, 8, WHITE),
            (5, 9, WHITE),
            (6, 9, WHITE),
            (7, 9, WHITE),
            (8, 9, WHITE),
        ],
    ),
]


class MeasuredAlphaBetaAI(AlphaBetaAI):
    """Evaluation-only AlphaBetaAI with lightweight search counters."""

    def _begin_search_stats(self) -> None:
        self.last_search_stats = {
            "nodes": 0,
            "root_calls": 0,
            "completed_depth": 0,
            "tactical_pairs": 0,
        }

    def _negamax(self, color, depth, alpha, beta, deadline):
        self.last_search_stats["nodes"] += 1
        return super()._negamax(color, depth, alpha, beta, deadline)

    def _root_search(self, color, count, depth, deadline):
        self.last_search_stats["root_calls"] += 1
        result = super()._root_search(color, count, depth, deadline)
        if result is not None:
            self.last_search_stats["completed_depth"] = max(
                self.last_search_stats["completed_depth"],
                depth,
            )
        return result

    def get_moves(self, board, color, count):
        self._begin_search_stats()
        moves = super().get_moves(board, color, count)
        return moves


class MeasuredAlphaBeltaPlusAI(AlphaBeltaPlusAI):
    """Evaluation-only AlphaBeltaPlusAI with the same counters."""

    def _begin_search_stats(self) -> None:
        self.last_search_stats = {
            "nodes": 0,
            "root_calls": 0,
            "completed_depth": 0,
            "tactical_pairs": 0,
        }

    def _negamax(self, color, depth, alpha, beta, deadline):
        self.last_search_stats["nodes"] += 1
        return super()._negamax(color, depth, alpha, beta, deadline)

    def _root_search(self, color, count, depth, deadline):
        self.last_search_stats["root_calls"] += 1
        result = super()._root_search(color, count, depth, deadline)
        if result is not None:
            self.last_search_stats["completed_depth"] = max(
                self.last_search_stats["completed_depth"],
                depth,
            )
        return result

    def get_moves(self, board, color, count):
        self._begin_search_stats()
        moves = super().get_moves(board, color, count)
        return moves

    def _add_tactical_pair_count(self, ranked) -> None:
        n = len(ranked)
        self.last_search_stats["tactical_pairs"] += max(0, n * (n - 1) // 2)

    def _find_pair_win(self, ranked, color, ci):
        self._add_tactical_pair_count(ranked)
        return super()._find_pair_win(ranked, color, ci)

    def _find_pair_threats(self, ranked, color, ci):
        self._add_tactical_pair_count(ranked)
        return super()._find_pair_threats(ranked, color, ci)


class MeasuredAlphaBeltaMaxAI(AlphaBeltaMaxAI, MeasuredAlphaBeltaPlusAI):
    """Evaluation-only AlphaBeltaMaxAI with the same counters."""

    def get_moves(self, board, color, count):
        self._begin_search_stats()
        return AlphaBeltaMaxAI.get_moves(self, board, color, count)

    def _root_search(self, color, count, depth, deadline):
        self.last_search_stats["root_calls"] += 1
        result = AlphaBeltaMaxAI._root_search(self, color, count, depth, deadline)
        if result is not None:
            self.last_search_stats["completed_depth"] = max(
                self.last_search_stats["completed_depth"],
                depth,
            )
        return result


def _make_challenger(name: str):
    if name == "alpha_belta_plus":
        return MeasuredAlphaBeltaPlusAI()
    if name == "alpha_belta_max":
        return MeasuredAlphaBeltaMaxAI()
    raise ValueError(f"unsupported challenger: {name}")


def _make_player_ai(name: str):
    if name == "alpha_beta":
        return MeasuredAlphaBetaAI()
    if name == "alpha_belta_plus":
        return MeasuredAlphaBeltaPlusAI()
    if name == "alpha_belta_max":
        return MeasuredAlphaBeltaMaxAI()
    raise ValueError(f"unsupported AI: {name}")


def _opp(color: int) -> int:
    return WHITE if color == BLACK else BLACK


def _next_color(history_len: int) -> int:
    if history_len == 0:
        return BLACK
    completed_turns = 1 + (history_len - 1) // 2
    return WHITE if completed_turns % 2 == 1 else BLACK


@contextmanager
def _temporary_think_time(seconds: float):
    old = alpha_beta_module._THINK_TIME
    alpha_beta_module._THINK_TIME = seconds
    try:
        yield
    finally:
        alpha_beta_module._THINK_TIME = old


def _apply_opening(board: Board, opening: Opening) -> None:
    for row, col, color in opening:
        if not board.place(Move(row, col, color)):
            raise ValueError(f"invalid opening move: {(row, col, color)}")


def _default_named_openings() -> List[NamedOpening]:
    return [
        NamedOpening(f"default_{index}", opening)
        for index, opening in enumerate(OPENINGS)
    ]


def _selected_openings(use_opening_suite: bool) -> List[NamedOpening]:
    return OPENING_SUITE if use_opening_suite else _default_named_openings()


def _collect_decision_summary(
    game_results: List[Dict[str, object]],
) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for game in game_results:
        for entry in game.get("move_log", []):
            ai_name = entry.get("ai_name")
            decision = entry.get("decision", {})
            if not ai_name or not isinstance(decision, dict):
                continue
            reason = decision.get("reason") or "unknown"
            ai_summary = summary.setdefault(str(ai_name), {})
            ai_summary[str(reason)] = ai_summary.get(str(reason), 0) + 1
    return summary


def _valid_ai_moves(board: Board, moves: Iterable[Move], color: int, count: int) -> List[Move]:
    valid: List[Move] = []
    seen = set()
    for move in moves:
        cell = (move.row, move.col)
        if move.color != color or cell in seen or not board.is_empty(move.row, move.col):
            continue
        seen.add(cell)
        valid.append(move)
        if len(valid) == count:
            break
    return valid


def play_game(
    black_ai,
    white_ai,
    opening: Optional[Opening] = None,
    max_turns: int = 120,
    think_time: float = 0.05,
    record_moves: bool = False,
) -> Dict[str, object]:
    board = Board(19)
    _apply_opening(board, opening or [])
    ai_by_color = {BLACK: black_ai, WHITE: white_ai}
    move_log: List[Dict[str, object]] = []

    with _temporary_think_time(think_time):
        for turn_index in range(max_turns):
            color = _next_color(len(board.history))
            count = stones_per_turn(len(board.history) + 1)
            ai = ai_by_color[color]
            start = time.perf_counter()
            raw_moves = ai.get_moves(board.copy(), color, count)
            elapsed_ms = (time.perf_counter() - start) * 1000
            moves = _valid_ai_moves(board, raw_moves, color, count)
            if record_moves:
                move_log.append(
                    {
                        "turn": turn_index + 1,
                        "ai_name": ai.name,
                        "color": color,
                        "moves": [(move.row, move.col) for move in moves],
                        "elapsed_ms": round(elapsed_ms, 3),
                        "decision": dict(getattr(ai, "last_decision", {})),
                        "stats": dict(
                            getattr(
                                ai,
                                "last_search_stats",
                                {
                                    "nodes": 0,
                                    "root_calls": 0,
                                    "completed_depth": 0,
                                },
                            )
                        ),
                    }
                )
            if len(moves) != count:
                return {
                    "winner": _opp(color),
                    "reason": "invalid",
                    "stones": len(board.history),
                    "move_log": move_log if record_moves else [],
                }

            for move in moves:
                board.place(move)
                won, _ = check_win(board, move)
                if won:
                    return {
                        "winner": color,
                        "reason": "win",
                        "stones": len(board.history),
                        "move_log": move_log if record_moves else [],
                    }

            if not board.get_all_empty():
                return {
                    "winner": None,
                    "reason": "draw",
                    "stones": len(board.history),
                    "move_log": move_log if record_moves else [],
                }

    return {
        "winner": None,
        "reason": "turn_limit",
        "stones": len(board.history),
        "move_log": move_log if record_moves else [],
    }


def run_matchup(
    challenger: str = "alpha_belta_plus",
    max_games: Optional[int] = None,
    max_turns: int = 120,
    think_time: float = 0.05,
    record_moves: bool = False,
    opening_suite: bool = False,
) -> Dict[str, object]:
    game_results: List[Dict[str, object]] = []

    for opening_index, named_opening in enumerate(_selected_openings(opening_suite)):
        for challenger_color in (BLACK, WHITE):
            if max_games is not None and len(game_results) >= max_games:
                break

            challenger_ai = _make_challenger(challenger)
            baseline_ai = MeasuredAlphaBetaAI()
            black_ai = challenger_ai if challenger_color == BLACK else baseline_ai
            white_ai = challenger_ai if challenger_color == WHITE else baseline_ai
            result = play_game(
                black_ai,
                white_ai,
                opening=named_opening.moves,
                max_turns=max_turns,
                think_time=think_time,
                record_moves=record_moves,
            )
            result["opening_index"] = opening_index
            result["opening_name"] = named_opening.name
            result["plus_color"] = challenger_color
            result["challenger_color"] = challenger_color
            game_results.append(result)

        if max_games is not None and len(game_results) >= max_games:
            break

    plus_wins = sum(
        1 for game in game_results if game["winner"] == game["plus_color"]
    )
    baseline_wins = sum(
        1
        for game in game_results
        if game["winner"] is not None and game["winner"] != game["plus_color"]
    )
    draws = sum(1 for game in game_results if game["winner"] is None)

    return {
        "challenger": challenger,
        "games": len(game_results),
        "plus_wins": plus_wins,
        "baseline_wins": baseline_wins,
        "draws": draws,
        "decision_summary": _collect_decision_summary(game_results),
        "game_results": game_results,
    }


def _collect_head_to_head_summary(
    ai_a: str,
    ai_b: str,
    game_results: List[Dict[str, object]],
) -> Dict[str, object]:
    ai_a_wins = sum(1 for game in game_results if game["winner"] == game["ai_a_color"])
    ai_b_wins = sum(
        1
        for game in game_results
        if game["winner"] is not None and game["winner"] != game["ai_a_color"]
    )
    draws = sum(1 for game in game_results if game["winner"] is None)
    return {
        "ai_a": ai_a,
        "ai_b": ai_b,
        "games": len(game_results),
        "ai_a_wins": ai_a_wins,
        "ai_b_wins": ai_b_wins,
        "draws": draws,
        "decision_summary": _collect_decision_summary(game_results),
        "game_results": game_results,
    }


def run_head_to_head(
    ai_a: str,
    ai_b: str,
    think_times: Iterable[float] = (0.05,),
    max_games: Optional[int] = None,
    max_turns: int = 120,
    record_moves: bool = False,
    opening_suite: bool = False,
) -> Dict[str, object]:
    game_results: List[Dict[str, object]] = []

    for think_time in think_times:
        for opening_index, named_opening in enumerate(_selected_openings(opening_suite)):
            for ai_a_color in (BLACK, WHITE):
                if max_games is not None and len(game_results) >= max_games:
                    return _collect_head_to_head_summary(ai_a, ai_b, game_results)

                player_a = _make_player_ai(ai_a)
                player_b = _make_player_ai(ai_b)
                black_ai = player_a if ai_a_color == BLACK else player_b
                white_ai = player_a if ai_a_color == WHITE else player_b
                result = play_game(
                    black_ai,
                    white_ai,
                    opening=named_opening.moves,
                    max_turns=max_turns,
                    think_time=think_time,
                    record_moves=record_moves,
                )
                result["opening_index"] = opening_index
                result["opening_name"] = named_opening.name
                result["ai_a_color"] = ai_a_color
                result["ai_b_color"] = _opp(ai_a_color)
                result["think_time"] = think_time
                game_results.append(result)

    return _collect_head_to_head_summary(ai_a, ai_b, game_results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare alpha-belta-plus with alpha_beta.")
    parser.add_argument(
        "--head-to-head",
        nargs=2,
        metavar=("AI_A", "AI_B"),
        choices=("alpha_beta", "alpha_belta_plus", "alpha_belta_max"),
    )
    parser.add_argument(
        "--challenger",
        choices=("alpha_belta_plus", "alpha_belta_max"),
        default="alpha_belta_plus",
    )
    parser.add_argument("--max-games", type=int, default=None)
    parser.add_argument("--max-turns", type=int, default=120)
    parser.add_argument("--think-time", type=float, default=0.05)
    parser.add_argument("--record-moves", action="store_true")
    parser.add_argument("--opening-suite", action="store_true")
    args = parser.parse_args()

    if args.head_to_head:
        result = run_head_to_head(
            ai_a=args.head_to_head[0],
            ai_b=args.head_to_head[1],
            think_times=[args.think_time],
            max_games=args.max_games,
            max_turns=args.max_turns,
            record_moves=args.record_moves,
            opening_suite=args.opening_suite,
        )
        print(
            "games={games} ai_a={ai_a} ai_b={ai_b} ai_a_wins={ai_a_wins} "
            "ai_b_wins={ai_b_wins} draws={draws}".format(**result)
        )
        for index, game in enumerate(result["game_results"], start=1):
            print(
                "game={index} opening={opening_name} ai_a_color={ai_a_color} winner={winner} "
                "reason={reason} stones={stones} think_time={think_time}".format(
                    index=index,
                    **game,
                )
            )
        if result["decision_summary"]:
            print(f"decision_summary={result['decision_summary']}")
        return

    result = run_matchup(
        challenger=args.challenger,
        max_games=args.max_games,
        max_turns=args.max_turns,
        think_time=args.think_time,
        record_moves=args.record_moves,
        opening_suite=args.opening_suite,
    )
    print(
        "games={games} plus_wins={plus_wins} baseline_wins={baseline_wins} "
        "draws={draws}".format(**result)
    )
    for index, game in enumerate(result["game_results"], start=1):
        print(
            "game={index} opening={opening_name} plus_color={plus_color} winner={winner} "
            "reason={reason} stones={stones}".format(index=index, **game)
        )
        if args.record_moves:
            for entry in game.get("move_log", []):
                stats = entry["stats"]
                decision_reason = entry.get("decision", {}).get("reason", "")
                entry_fields = dict(entry)
                entry_fields.pop("decision", None)
                print(
                    "  turn={turn} ai={ai_name} color={color} moves={moves} "
                    "elapsed_ms={elapsed_ms} root_calls={root_calls} "
                    "nodes={nodes} depth={completed_depth} "
                    "tactical_pairs={tactical_pairs} decision={decision}".format(
                        nodes=stats.get("nodes", 0),
                        root_calls=stats.get("root_calls", 0),
                        completed_depth=stats.get("completed_depth", 0),
                        tactical_pairs=stats.get("tactical_pairs", 0),
                        decision=decision_reason,
                        **entry_fields,
                    )
                )
    if result["decision_summary"]:
        print(f"decision_summary={result['decision_summary']}")


if __name__ == "__main__":
    main()
