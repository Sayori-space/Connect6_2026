"""
Opening book generator — uses KataGomo engine to find strongest responses
for various Connect6 opening positions.

Usage: py -3 scripts/gen_opening_book.py
"""

import sys
import os
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.kata_gomo_ai import KataGomoAI
from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE


def make_board(moves_list):
    board = Board(19)
    for r, c, clr in moves_list:
        if not board.place(Move(r, c, clr)):
            print(f"  WARNING: Failed to place ({r},{c},{'B' if clr==BLACK else 'W'})")
    return board


def desc_color(clr):
    return "BLACK" if clr == BLACK else "WHITE"


def show_board(board):
    """Print a text representation of the board."""
    print("   " + " ".join(chr(ord('a') + c) for c in range(19)))
    for r in range(19):
        row = f"{19 - r:2d} "
        for c in range(19):
            val = board.get(r, c)
            if val == BLACK:
                row += "X "
            elif val == WHITE:
                row += "O "
            else:
                row += ". "
        print(row[:-1])


# ============================================================
# Define all opening positions to evaluate
# ============================================================
positions = []

# White's 3rd turn (move 4) vs common Black 3rd-turn moves

positions.append(("W_vs_diag_cross",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (8, 10, BLACK), (10, 8, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black diagonal cross"))

positions.append(("W_vs_B_vertical",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (7, 9, BLACK), (11, 9, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black vertical (7,9)+(11,9)"))

positions.append(("W_vs_B_horizontal",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (9, 7, BLACK), (9, 11, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black horizontal (9,7)+(9,11)"))

positions.append(("W_vs_B_diag_extend",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (7, 7, BLACK), (11, 11, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black diag-extend (7,7)+(11,11)"))

positions.append(("W_vs_B_split_vert",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (8, 9, BLACK), (10, 9, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black split-vertical (8,9)+(10,9)"))

positions.append(("W_vs_B_split_horiz",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (9, 8, BLACK), (9, 10, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black split-horizontal (9,8)+(9,10)"))

positions.append(("W_vs_B_asym1",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (7, 8, BLACK), (11, 12, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black asymmetric (7,8)+(11,12)"))

positions.append(("W_vs_B_asym2",
    [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE), (8, 7, BLACK), (10, 13, BLACK)],
    WHITE, 2, "White's 3rd turn vs Black asymmetric (8,7)+(10,13)"))


print("=" * 70)
print("  OPENING BOOK GENERATOR")
print("  Using KataGomo MCTS engine")
print("=" * 70)

# Initialize engine
print("\nInitializing KataGomoAI (max_visits=800)...")
ai = KataGomoAI(max_visits=800)

if ai._engine_ok:
    print("Engine OK! Running evaluations...\n")
else:
    print("Engine not available; will use AlphaBeltaMaxAI fallback\n")

ab = AlphaBeltaMaxAI()
ab.think_time_seconds = 0.5

all_results = {}

for name, moves_list, color, count, desc in positions:
    board = make_board(moves_list)

    print("\n" + "=" * 70)
    print(f"  Position: {name}")
    print(f"  {desc}")
    print(f"  To move: {desc_color(color)} ({count} stones)")

    show_board(board)

    kata_runs = []
    kata_reasons = []

    for run_idx in range(3):
        t0 = time.monotonic()
        result = ai.get_moves(board, color, count)
        elapsed = time.monotonic() - t0
        cells = tuple(sorted((m.row, m.col) for m in result))
        reason = ai.last_decision.get("reason", "?")
        kata_runs.append(cells)
        kata_reasons.append(reason)
        print(f"    Run {run_idx + 1}: {list(cells)}  (reason={reason}, {elapsed:.2f}s)")

    # AlphaBeltaMax comparison
    t0 = time.monotonic()
    ab_result = ab.get_moves(board, color, count)
    ab_elapsed = time.monotonic() - t0
    ab_cells = tuple(sorted((m.row, m.col) for m in ab_result))
    ab_reason = ab.last_decision.get("reason", "?")
    print(f"    ALPHA-BELTA-MAX: {list(ab_cells)}  (reason={ab_reason}, {ab_elapsed:.2f}s)")

    counted = Counter(kata_runs)
    mc = counted.most_common(1)[0]
    print(f"  >> KATA MOST COMMON: {list(mc[0])} ({mc[1]}/3)")

    all_results[name] = {
        "kata_runs": [list(r) for r in kata_runs],
        "kata_reasons": kata_reasons,
        "kata_best": list(mc[0]),
        "kata_consistency": f"{mc[1]}/3",
        "ab_cells": list(ab_cells),
        "ab_reason": ab_reason,
    }

# Deep line: Black's 4th turn after the diagonal cross + White's best response
# First determine what White's best response is
w_best = all_results.get("W_vs_diag_cross", {}).get("kata_best", None)
if w_best and len(w_best) == 2:
    print("\n" + "=" * 70)
    print("  DEEP LINE: Black's 4th turn after diagonal cross + White's best response")
    print(f"  White's best response (from above): {w_best}")

    deep_moves = [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE),
                  (8, 10, BLACK), (10, 8, BLACK),
                  (w_best[0][0], w_best[0][1], WHITE),
                  (w_best[1][0], w_best[1][1], WHITE)]

    deep_board = make_board(deep_moves)
    show_board(deep_board)

    deep_runs = []
    for run_idx in range(3):
        t0 = time.monotonic()
        result = ai.get_moves(deep_board, BLACK, 2)
        elapsed = time.monotonic() - t0
        cells = tuple(sorted((m.row, m.col) for m in result))
        reason = ai.last_decision.get("reason", "?")
        deep_runs.append(cells)
        print(f"    Run {run_idx + 1}: {list(cells)}  (reason={reason}, {elapsed:.2f}s)")

    counted = Counter(deep_runs)
    mc = counted.most_common(1)[0]
    print(f"  >> KATA MOST COMMON: {list(mc[0])} ({mc[1]}/3)")

    all_results["B_turn4_deep"] = {
        "kata_runs": [list(r) for r in deep_runs],
        "kata_best": list(mc[0]),
        "kata_consistency": f"{mc[1]}/3",
    }

    # Also try alternative White responses for deeper lines
    # If White's second most common was different, try that too
    if len(counted) > 1:
        second = counted.most_common(2)[1]
        second_white = second[0]
        print(f"\n  Also trying second White response: {list(second_white)}")

        deep2_moves = [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE),
                       (8, 10, BLACK), (10, 8, BLACK),
                       (second_white[0][0], second_white[0][1], WHITE),
                       (second_white[1][0], second_white[1][1], WHITE)]
        deep2_board = make_board(deep2_moves)

        deep2_runs = []
        for run_idx in range(3):
            t0 = time.monotonic()
            result = ai.get_moves(deep2_board, BLACK, 2)
            elapsed = time.monotonic() - t0
            cells = tuple(sorted((m.row, m.col) for m in result))
            deep2_runs.append(cells)
            print(f"    Run {run_idx + 1}: {list(cells)}  (reason={ai.last_decision.get('reason', '?')}, {elapsed:.2f}s)")

        counted2 = Counter(deep2_runs)
        mc2 = counted2.most_common(1)[0]
        print(f"  >> KATA MOST COMMON: {list(mc2[0])} ({mc2[1]}/3)")

        all_results["B_turn4_deep_alt"] = {
            "kata_runs": [list(r) for r in deep2_runs],
            "kata_best": list(mc2[0]),
            "kata_consistency": f"{mc2[1]}/3",
        }

# Also try Black's 4th turn from the vertical line
w_vs_vert = all_results.get("W_vs_B_vertical", {}).get("kata_best", None)
if w_vs_vert and len(w_vs_vert) == 2:
    print("\n" + "=" * 70)
    print("  DEEP LINE: Black's 4th turn in vertical line")
    print(f"  White's best response: {w_vs_vert}")

    deep3_moves = [(9, 9, BLACK), (8, 8, WHITE), (10, 10, WHITE),
                   (7, 9, BLACK), (11, 9, BLACK),
                   (w_vs_vert[0][0], w_vs_vert[0][1], WHITE),
                   (w_vs_vert[1][0], w_vs_vert[1][1], WHITE)]
    deep3_board = make_board(deep3_moves)
    show_board(deep3_board)

    deep3_runs = []
    for run_idx in range(3):
        t0 = time.monotonic()
        result = ai.get_moves(deep3_board, BLACK, 2)
        elapsed = time.monotonic() - t0
        cells = tuple(sorted((m.row, m.col) for m in result))
        deep3_runs.append(cells)
        print(f"    Run {run_idx + 1}: {list(cells)}  (reason={ai.last_decision.get('reason', '?')}, {elapsed:.2f}s)")

    counted3 = Counter(deep3_runs)
    mc3 = counted3.most_common(1)[0]
    print(f"  >> KATA MOST COMMON: {list(mc3[0])} ({mc3[1]}/3)")

    all_results["B_turn4_vertical_line"] = {
        "kata_runs": [list(r) for r in deep3_runs],
        "kata_best": list(mc3[0]),
        "kata_consistency": f"{mc3[1]}/3",
    }


print("\n\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
for name, data in all_results.items():
    print(f"\n  {name}:")
    print(f"    KataGomo: {data.get('kata_best', 'N/A')} (consistency: {data.get('kata_consistency', 'N/A')})")
    if 'ab_cells' in data:
        print(f"    AlphaBeltaMax: {data['ab_cells']} (reason: {data.get('ab_reason', 'N/A')})")
    if 'kata_reasons' in data:
        print(f"    Reasons: {data['kata_reasons']}")

print("\nDone!")
