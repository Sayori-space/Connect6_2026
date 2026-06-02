"""KataGomo self-play — generate game records for eval analysis.

Runs KataGomo vs KataGomo, saves each game to chess_manual/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.kata_gomo_ai import KataGomoAI
from game.game_manager import GameManager, GameState
from models.game_config import GameConfig
from models.player import PlayerType
from utils.constants import BLACK, WHITE


def _save_game_record(manager: GameManager, game_idx: int, elapsed: float) -> str:
    chess_dir = os.path.join(_REPO_ROOT, "chess_manual")
    os.makedirs(chess_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"kata_selfplay_{ts}_g{game_idx}.json"
    filepath = os.path.join(chess_dir, filename)

    moves = []
    for mv in manager.board.history:
        moves.append({
            "color": "B" if mv.color == BLACK else "W",
            "row": mv.row,
            "col": mv.col,
        })

    record = {
        "game_index": game_idx,
        "timestamp": ts,
        "black_engine": "KataGomo",
        "white_engine": "KataGomo",
        "winner": manager.winner,
        "moves": moves,
        "total_moves": len(moves),
        "elapsed_seconds": round(elapsed, 2),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"  Saved: {filename}")
    return filepath


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


def run_kata_self_play_game(
    black_ai: KataGomoAI,
    white_ai: KataGomoAI,
    max_turns: int = 200,
    game_idx: int = 1,
) -> dict:
    config = GameConfig(
        black_type=PlayerType.AI,
        white_type=PlayerType.AI,
        black_name="KataGomo",
        white_name="KataGomo",
    )
    manager = GameManager(config)

    started = time.monotonic()
    manager.start()
    turns = 0

    while manager.state == GameState.WAITING and turns < max_turns:
        color = manager.current_color
        needed = manager.stones_needed_this_turn
        ai = black_ai if color == BLACK else white_ai

        moves = ai.get_moves(manager.board.copy(), color, needed)

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

        turns += 1

    elapsed = time.monotonic() - started
    filepath = _save_game_record(manager, game_idx, elapsed)

    return {
        "game_index": game_idx,
        "winner": manager.winner,
        "turns": turns,
        "stones": len(manager.board.history),
        "elapsed": round(elapsed, 2),
        "file": filepath,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="KataGomo self-play")
    parser.add_argument("--games", type=int, default=4,
                        help="Number of games (default: 4)")
    parser.add_argument("--visits", type=int, default=500,
                        help="Max visits per move (default: 500)")
    parser.add_argument("--max-turns", type=int, default=200,
                        help="Max turns per game (default: 200)")
    args = parser.parse_args()

    print(f"KataGomo self-play: {args.games} games, {args.visits} visits\n")

    results = []
    for i in range(1, args.games + 1):
        print(f"--- Game {i}/{args.games} ---")

        black_ai = KataGomoAI(max_visits=args.visits)
        white_ai = KataGomoAI(max_visits=args.visits)

        try:
            result = run_kata_self_play_game(black_ai, white_ai,
                                             max_turns=args.max_turns,
                                             game_idx=i)
            results.append(result)

            winner_str = {BLACK: "Black", WHITE: "White", None: "Draw"}
            print(f"  Winner: {winner_str.get(result['winner'], '?')}, "
                  f"stones={result['stones']}, "
                  f"elapsed={result['elapsed']:.1f}s")
        finally:
            del black_ai
            del white_ai

    print(f"\n=== Summary ===")
    black_wins = sum(1 for r in results if r["winner"] == BLACK)
    white_wins = sum(1 for r in results if r["winner"] == WHITE)
    draws = sum(1 for r in results if r["winner"] is None)
    total_elapsed = sum(r["elapsed"] for r in results)
    print(f"  Black: {black_wins}, White: {white_wins}, Draws: {draws}")
    print(f"  Total time: {total_elapsed:.1f}s")
    print(f"  Records saved to chess_manual/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
