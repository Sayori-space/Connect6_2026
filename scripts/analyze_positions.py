"""Analyze KataGomo self-play records — compare AlphaBeltaMaxAI move choices.

Replays each position and checks whether AlphaBeltaMaxAI would pick the same move
as KataGomo. Flags disagreements for eval improvement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from ai.kata_gomo_ai import KataGomoAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE

_COL_LABELS = "ABCDEFGHJKLMNOPQRST"


def _rc_label(r: int, c: int) -> str:
    return f"{_COL_LABELS[c]}{r + 1}"


def _load_game(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _analyse_position(
    board: Board,
    color: int,
    count: int,
    kata_move: Tuple[int, int],
    ab_ai: AlphaBeltaMaxAI,
    kata_ai: Optional[KataGomoAI],
) -> dict:
    """Analyse one position: what does AlphaBeltaMaxAI think vs KataGomo's choice."""
    ab_moves = ab_ai.get_moves(board.copy(), color, count)
    ab_decision = getattr(ab_ai, "last_decision", {})
    ab_stats = getattr(ab_ai, "last_search_stats", {})
    ab_ranked = getattr(ab_ai, "_ranked_cache", {})

    ab_top = [(m.row, m.col) for m in ab_moves]

    match = kata_move in ab_top

    # Get KataGomo's full ranking (if engine available)
    kata_ranking: List[dict] = []
    if kata_ai is not None and kata_ai._engine_ok:
        engine_result = kata_ai._query_engine(board, color, count)
        if engine_result:
            kata_ranking = [{"cell": rc, "label": _rc_label(*rc)}
                           for rc in engine_result[:10]]

    return {
        "kata_move": kata_move,
        "kata_label": _rc_label(*kata_move),
        "ab_top_moves": [(r, c) for r, c in ab_top[:5]],
        "ab_top_labels": [_rc_label(r, c) for r, c in ab_top[:5]],
        "ab_decision_reason": ab_decision.get("reason", ""),
        "ab_nodes": ab_stats.get("nodes", 0),
        "ab_depth": ab_stats.get("completed_depth", 0),
        "ab_ranked_count": len(ab_ranked),
        "match": match,
        "match_rank": (
            ab_top.index(kata_move) + 1
            if kata_move in ab_top else None
        ),
        "kata_ranking": kata_ranking,
    }


def _label_result(result: dict) -> str:
    if result["match"]:
        rank = result["match_rank"]
        return f"MATCH (rank #{rank})"
    return "MISMATCH"


def analyze_game(
    filepath: str,
    ab_ai: AlphaBeltaMaxAI,
    kata_ai: Optional[KataGomoAI] = None,
    max_positions: int = 0,
    verbose: bool = False,
) -> dict:
    record = _load_game(filepath)
    moves = record["moves"]
    total_positions = len(moves)

    if max_positions > 0 and total_positions > max_positions:
        # Analyse evenly spaced positions
        step = total_positions // max_positions
        analyse_indices = set(range(0, total_positions, max(1, step)))
    else:
        analyse_indices = set(range(total_positions))

    board = Board(19)
    results: List[dict] = []
    matches = 0

    for i, mv_data in enumerate(moves):
        color = BLACK if mv_data["color"] == "B" else WHITE
        r, c = mv_data["row"], mv_data["col"]
        kata_move = (r, c)

        if i in analyse_indices:
            # Determine how many stones to place at this position
            # Turn 0: first move = 1 stone (black)
            # After that: 2 stones per turn
            stones_before = i
            if stones_before == 0:
                count = 1
            else:
                gm_turn = (stones_before - 1) // 2 + 2  # gm turn number
                count = 1 if gm_turn == 1 else 2

            # For positions that are mid-turn (1 stone placed, 1 remaining),
            # we just analyze as if placing the remaining stone(s)
            result = _analyse_position(board, color, count, kata_move,
                                       ab_ai, kata_ai)
            result["turn_index"] = i
            result["color"] = "B" if color == BLACK else "W"
            results.append(result)

            if result["match"]:
                matches += 1

            if verbose:
                status = _label_result(result)
                print(f"  turn {i:3d} {result['color']}  kata={result['kata_label']:>4s}  "
                      f"ab={','.join(result['ab_top_labels'][:3]):<15s}  {status}")

        # Apply the move to advance board state
        board.place(Move(r, c, color))

    total = len(results)
    match_pct = (matches / total * 100) if total > 0 else 0

    return {
        "file": filepath,
        "total_positions": total_positions,
        "analysed": total,
        "matches": matches,
        "mismatches": total - matches,
        "match_pct": round(match_pct, 1),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare AlphaBeltaMaxAI vs KataGomo move choices")
    parser.add_argument("record", nargs="+",
                        help="Game record JSON file(s) to analyse")
    parser.add_argument("--max-positions", type=int, default=0,
                        help="Max positions per game (0 = all)")
    parser.add_argument("--with-kata", action="store_true",
                        help="Also query KataGomo at each position for full ranking")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-position results")
    parser.add_argument("--output", "-o", type=str, default="",
                        help="Save detailed results to JSON file")
    args = parser.parse_args()

    ab_ai = AlphaBeltaMaxAI()

    kata_ai = None
    if args.with_kata:
        kata_ai = KataGomoAI(max_visits=100)
        if not kata_ai._engine_ok:
            print("Warning: KataGomo engine not available, skipping kata ranking")

    try:
        all_analyses = []
        total_matches = 0
        total_analysed = 0

        for filepath in args.record:
            print(f"\nAnalyzing: {filepath}")
            analysis = analyze_game(
                filepath, ab_ai, kata_ai,
                max_positions=args.max_positions,
                verbose=args.verbose,
            )
            all_analyses.append(analysis)
            total_matches += analysis["matches"]
            total_analysed += analysis["analysed"]
            print(f"  Match rate: {analysis['match_pct']}% "
                  f"({analysis['matches']}/{analysis['analysed']})")

        if len(args.record) > 1:
            overall = (total_matches / total_analysed * 100
                      if total_analysed > 0 else 0)
            print(f"\nOverall: {overall:.1f}% ({total_matches}/{total_analysed})")

        if args.output:
            output = {
                "overall_match_pct": (
                    round(total_matches / total_analysed * 100, 1)
                    if total_analysed > 0 else 0
                ),
                "analyses": [
                    {k: v for k, v in a.items() if k != "results"}
                    for a in all_analyses
                ],
                "mismatches": [
                    r for a in all_analyses
                    for r in a["results"] if not r["match"]
                ],
            }
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"Saved detailed results to {args.output}")

    finally:
        if kata_ai is not None:
            del kata_ai

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
