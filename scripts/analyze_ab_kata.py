"""Analyze ABKataAI vs KataGomo self-play records."""
import json, os, sys, time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.ab_kata_ai import ABKataAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE

_COL = "ABCDEFGHJKLMNOPQRST"


def _label(r, c):
    return f"{_COL[c]}{r + 1}"


def analyze(filepath, ai, max_positions=0):
    with open(filepath) as f:
        record = json.load(f)

    moves = record["moves"]
    total = len(moves)
    indices = set(range(total))
    if max_positions > 0 and total > max_positions:
        step = total // max_positions
        indices = set(range(0, total, max(1, step)))

    board = Board(19)
    results = []
    matches = 0

    for i, mv in enumerate(moves):
        color = BLACK if mv["color"] == "B" else WHITE
        r, c = mv["row"], mv["col"]
        kata_move = (r, c)

        if i in indices:
            stones_before = i
            if stones_before == 0:
                count = 1
            else:
                gm_turn = (stones_before - 1) // 2 + 2
                count = 1 if gm_turn == 1 else 2

            ai_moves = ai.get_moves(board.copy(), color, count)
            ab_top = [(m.row, m.col) for m in ai_moves]
            decision = getattr(ai, "last_decision", {})

            match = kata_move in ab_top
            if match:
                matches += 1

            results.append({
                "turn": i,
                "color": mv["color"],
                "kata": _label(r, c),
                "ab_top": [_label(rr, cc) for rr, cc in ab_top[:3]],
                "match": match,
                "reason": decision.get("reason", ""),
                "nodes": getattr(ai, "last_search_stats", {}).get("nodes", 0),
            })

        board.place(Move(r, c, color))

    n = len(results)
    return {
        "file": os.path.basename(filepath),
        "total": total,
        "analysed": n,
        "matches": matches,
        "rate": round(matches / n * 100, 1) if n else 0,
        "results": results,
    }


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("records", nargs="+")
    p.add_argument("--visits", type=int, default=100)
    p.add_argument("--max-positions", type=int, default=0)
    p.add_argument("-o", type=str, default="")
    args = p.parse_args()

    ai = ABKataAI(max_visits=args.visits)
    if not ai._model_loaded:
        print("Engine not loaded!")
        return 1

    try:
        all_results = []
        total_matches = total_analysed = 0
        for fp in args.records:
            print(f"\nAnalyzing: {fp}")
            r = analyze(fp, ai, args.max_positions)
            all_results.append(r)
            total_matches += r["matches"]
            total_analysed += r["analysed"]
            print(f"  Match rate: {r['rate']}% ({r['matches']}/{r['analysed']})")
            print(f"  Hits: {ai._hits}, Misses: {ai._misses}")

        overall = round(total_matches / total_analysed * 100, 1) if total_analysed else 0
        print(f"\nOverall: {overall}% ({total_matches}/{total_analysed})")
        print(f"Cache: {ai._hits} hits, {ai._misses} misses")

        if args.o:
            with open(args.o, "w") as f:
                json.dump({"overall": overall, "analyses": [
                    {k: v for k, v in a.items() if k != "results"} for a in all_results
                ]}, f, ensure_ascii=False, indent=2)
    finally:
        del ai
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
