"""
收集 KataGo 引擎 policy 数据，分析候选排序一致性。

使用持久引擎进程（stderr 合并到 stdout 避免死锁）。
用法：
    py -3 scripts/collect_policy_data.py [--max-visits N]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE, EMPTY

_COL_LABELS = "abcdefghjklmnopqrst"

ENGINE_PATH = os.path.join(_REPO_ROOT, "ai", "kata_src", "cpp", "katago.exe")
MODEL_PATH = os.path.join(_REPO_ROOT, "ai", "models", "kata", "connectsix19x_b18trans.bin.gz")
CONFIG_PATH = os.path.join(_REPO_ROOT, "ai", "models", "kata", "analysis.cfg")


@dataclass
class PolicySample:
    position_id: str
    description: str
    color: int
    count: int
    moves_on_board: int
    engine_top8: List[Tuple[str, float, int]]
    static_top8: List[Tuple[int, int]]
    top8_overlap: int
    static_vs_engine: List[float]


# ---------------------------------------------------------------------------
# 局面定义 (15 个中盘局面)
# ---------------------------------------------------------------------------

def _p(r, c, color):
    return (r, c, color)

# 局面定义：moves 按 Connect6 落子顺序（B=1, W=2, B=2, W=2, ...）
# 总子数 = 3, 7, 11, 15, 19, 23, ...（White 刚走完，Black 走 2 子）
# 子序列：B, W,W, B,B, W,W, B,B, W,W, ...

POSITIONS = [
    dict(id="pos01_early_dev", desc="Early development (3 stones)",
         moves=[_p(9,9,BLACK), _p(10,10,WHITE), _p(10,9,WHITE)],
         color=BLACK, count=2),
    dict(id="pos02_horiz_dev", desc="Horizontal development (3 stones)",
         moves=[_p(9,9,BLACK), _p(9,10,WHITE), _p(9,8,WHITE)],
         color=BLACK, count=2),
    dict(id="pos03_diag_dev", desc="Diagonal development (3 stones)",
         moves=[_p(9,9,BLACK), _p(8,7,WHITE), _p(10,11,WHITE)],
         color=BLACK, count=2),
    dict(id="pos04_cross_dev", desc="Cross extension (7 stones)",
         moves=[_p(9,9,BLACK),  # B1
                _p(8,10,WHITE), _p(10,8,WHITE),  # W2, W3
                _p(9,8,BLACK), _p(10,9,BLACK),  # B4, B5
                _p(9,10,WHITE), _p(10,10,WHITE)],  # W6, W7
         color=BLACK, count=2),
    dict(id="pos05_horiz_fight", desc="Horizontal fight (7 stones)",
         moves=[_p(9,9,BLACK),
                _p(9,5,WHITE), _p(9,6,WHITE),
                _p(9,7,BLACK), _p(9,8,BLACK),
                _p(9,10,WHITE), _p(9,11,WHITE)],
         color=BLACK, count=2),
    dict(id="pos06_vert_fight", desc="Vertical fight (7 stones)",
         moves=[_p(9,9,BLACK),
                _p(5,9,WHITE), _p(6,9,WHITE),
                _p(7,9,BLACK), _p(8,9,BLACK),
                _p(10,9,WHITE), _p(11,9,WHITE)],
         color=BLACK, count=2),
    dict(id="pos07_edge_play", desc="Edge play (7 stones)",
         moves=[_p(3,3,BLACK),
                _p(2,3,WHITE), _p(2,4,WHITE),
                _p(3,4,BLACK), _p(3,5,BLACK),
                _p(4,3,WHITE), _p(4,4,WHITE)],
         color=BLACK, count=2),
    dict(id="pos08_center_cluster", desc="Center cluster (11 stones)",
         moves=[_p(9,9,BLACK),
                _p(8,8,WHITE), _p(10,10,WHITE),
                _p(8,10,BLACK), _p(10,8,BLACK),
                _p(7,9,WHITE), _p(11,9,WHITE),
                _p(9,7,BLACK), _p(9,11,BLACK),
                _p(8,9,WHITE), _p(10,9,WHITE)],
         color=BLACK, count=2),
    dict(id="pos09_diag_fight", desc="Diagonal fight (7 stones)",
         moves=[_p(9,9,BLACK),
                _p(6,6,WHITE), _p(7,7,WHITE),
                _p(8,8,BLACK), _p(5,5,BLACK),
                _p(10,10,WHITE), _p(11,11,WHITE)],
         color=BLACK, count=2),
    dict(id="pos10_connect_cut", desc="Connect and cut (11 stones)",
         moves=[_p(9,9,BLACK),
                _p(8,10,WHITE), _p(10,8,WHITE),
                _p(8,8,BLACK), _p(10,10,BLACK),
                _p(7,9,WHITE), _p(11,9,WHITE),
                _p(9,7,BLACK), _p(9,11,BLACK),
                _p(6,8,WHITE), _p(12,10,WHITE)],
         color=BLACK, count=2),
    dict(id="pos11_gap_pattern", desc="Gap pattern (7 stones)",
         moves=[_p(9,9,BLACK),
                _p(5,5,WHITE), _p(5,6,WHITE),
                _p(5,7,BLACK), _p(5,9,BLACK),
                _p(6,5,WHITE), _p(6,6,WHITE)],
         color=BLACK, count=2),
    dict(id="pos12_dense_fight", desc="Dense fight (11 stones)",
         moves=[_p(9,9,BLACK),
                _p(8,9,WHITE), _p(9,8,WHITE),
                _p(9,10,BLACK), _p(10,9,BLACK),
                _p(8,8,WHITE), _p(10,10,WHITE),
                _p(7,9,BLACK), _p(9,7,BLACK),
                _p(8,10,WHITE), _p(10,8,WHITE)],
         color=BLACK, count=2),
    dict(id="pos13_two_front", desc="Two-front battle (11 stones)",
         moves=[_p(9,9,BLACK),
                _p(4,4,WHITE), _p(4,5,WHITE),
                _p(4,6,BLACK), _p(5,4,BLACK),
                _p(14,14,WHITE), _p(14,13,WHITE),
                _p(5,5,BLACK), _p(6,4,BLACK),
                _p(13,13,WHITE), _p(14,12,WHITE)],
         color=BLACK, count=2),
    dict(id="pos14_open_mid", desc="Open midgame (15 stones)",
         moves=[_p(9,9,BLACK),
                _p(8,8,WHITE), _p(10,10,WHITE),
                _p(8,10,BLACK), _p(10,8,BLACK),
                _p(7,9,WHITE), _p(11,9,WHITE),
                _p(9,7,BLACK), _p(9,11,BLACK),
                _p(6,8,WHITE), _p(12,10,WHITE),
                _p(5,7,BLACK), _p(13,11,BLACK),
                _p(4,6,WHITE), _p(14,12,WHITE)],
         color=BLACK, count=2),
    dict(id="pos15_large", desc="Large midgame (19 stones)",
         moves=[_p(9,9,BLACK),
                _p(8,8,WHITE), _p(10,10,WHITE),
                _p(8,10,BLACK), _p(10,8,BLACK),
                _p(7,7,WHITE), _p(11,11,WHITE),
                _p(6,6,BLACK), _p(12,12,BLACK),
                _p(5,5,WHITE), _p(13,13,WHITE),
                _p(5,7,BLACK), _p(13,11,BLACK),
                _p(4,6,WHITE), _p(14,12,WHITE),
                _p(4,4,BLACK), _p(14,14,BLACK),
                _p(3,5,WHITE), _p(15,13,WHITE)],
         color=BLACK, count=2),
]


# ---------------------------------------------------------------------------
# 引擎查询（持久进程）
# ---------------------------------------------------------------------------

class EngineClient:
    def __init__(self, max_visits=20):
        self._process: Optional[subprocess.Popen] = None
        self._max_visits = max_visits
        self._ok = False

    def start(self) -> bool:
        if not os.path.exists(ENGINE_PATH):
            return False
        try:
            self._process = subprocess.Popen(
                [ENGINE_PATH, "analysis", "-config", CONFIG_PATH, "-model", MODEL_PATH],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except Exception as e:
            print(f"  Engine start error: {e}")
            return False

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = self._process.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            if "ready" in line.lower() and "begin" in line.lower():
                self._ok = True
                print(f"  [Engine] Ready (maxVisits={self._max_visits})")
                return True

        print("  [Engine] Startup timeout")
        return False

    def analyze(self, id, board, color) -> Optional[List[Tuple[str, float, int]]]:
        if not self._ok or self._process is None:
            return None

        moves_json = []
        for mv in board.history:
            col = _COL_LABELS[mv.col]
            row = str(19 - mv.row)
            stone = "B" if mv.color == BLACK else "W"
            moves_json.append([stone, col + row])

        player = "B" if color == BLACK else "W"
        turn = len(board.history)

        try:
            request = json.dumps({
                "id": str(id),
                "rules": {"basicRule": "FREESTYLE"},
                "boardXSize": 19, "boardYSize": 19,
                "moves": moves_json,
                "analyzeTurns": [turn],
                "maxVisits": self._max_visits,
                "player": player,
            })
            self._process.stdin.write(request + "\n")
            self._process.stdin.flush()

            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                line = self._process.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in resp:
                    return None
                mis = resp.get("moveInfos", [])
                return [(mi.get("move", ""), mi.get("prior", 0.0), mi.get("visits", 0))
                        for mi in mis if mi.get("move")]
            return None
        except Exception as e:
            print(f"  [Engine] Query error: {e}")
            return None

    def close(self):
        if self._process is not None:
            try:
                self._process.stdin.close()
                self._process.stdout.close()
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 静态排序分析
# ---------------------------------------------------------------------------

def static_analysis(board, color, count, top_n=8):
    ai = AlphaBeltaMaxAI()
    ai._init_from_board(board)
    ci = 0 if color == BLACK else 1
    cands = ai._candidates()
    ranked = ai._sorted_cands(cands, ci, len(cands))
    return ranked[:top_n]


def gtp_to_rc(move_str):
    if not move_str or len(move_str) < 2:
        return -1, -1
    col_letter = move_str[0].lower()
    c = ord(col_letter) - ord("a")
    if c > 7:
        c -= 1
    try:
        r = 19 - int(move_str[1:])
    except ValueError:
        return -1, -1
    return r, c


def analyze_consistency(engine_top8, static_top8):
    engine_set = {}
    for rank, (move_str, prior, visits) in enumerate(engine_top8):
        r, c = gtp_to_rc(move_str)
        if r >= 0 and c >= 0:
            engine_set[(r, c)] = (rank, prior)
    overlap = 0
    penalties = []
    for cell in static_top8:
        if cell in engine_set:
            overlap += 1
            rank, _ = engine_set[cell]
            penalties.append(rank / max(1, len(engine_top8) - 1))
        else:
            penalties.append(1.0)
    return overlap, penalties


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-visits", type=int, default=20)
    parser.add_argument("--output", default=None)
    parser.add_argument("--only-static", action="store_true",
                        help="Skip engine queries, only show static analysis")
    args = parser.parse_args()

    output_path = args.output or os.path.join(_REPO_ROOT, "policy_analysis.json")

    print(f"Total positions: {len(POSITIONS)}")
    sys.stdout.flush()

    # Start engine
    engine = EngineClient(max_visits=args.max_visits)
    engine_ok = False if args.only_static else engine.start()

    # Analyze each position
    samples = []
    engine_ok_count = 0

    for idx, pos in enumerate(POSITIONS):
        pos_id = pos["id"]
        print(f"\n[{idx+1}/{len(POSITIONS)}] {pos_id}: {pos['desc']}")
        sys.stdout.flush()

        board = Board(19)
        for r, c, clr in pos["moves"]:
            board.place(Move(r, c, clr))

        static_top8 = static_analysis(board, pos["color"], pos["count"])
        print(f"  Static top-8: {static_top8}")
        sys.stdout.flush()

        if args.only_static:
            samples.append(PolicySample(
                position_id=pos_id, description=pos["desc"],
                color=pos["color"], count=pos["count"],
                moves_on_board=len(pos["moves"]),
                engine_top8=[], static_top8=static_top8,
                top8_overlap=0, static_vs_engine=[1.0]*8,
            ))
            continue

        engine_data = engine.analyze(str(idx), board, pos["color"])
        engine_top8 = []

        if engine_data:
            engine_ok_count += 1
            for ms, pr, v in engine_data[:8]:
                r, c = gtp_to_rc(ms)
                engine_top8.append((ms, pr, v))
                print(f"  Engine: {ms} ({r},{c}) prior={pr:.4f} v={v}")
            sys.stdout.flush()
        else:
            print(f"  Engine: no data")
            sys.stdout.flush()

        overlap, penalties = analyze_consistency(engine_top8, static_top8)
        print(f"  Overlap: {overlap}/8")
        sys.stdout.flush()

        samples.append(PolicySample(
            position_id=pos_id, description=pos["desc"],
            color=pos["color"], count=pos["count"],
            moves_on_board=len(pos["moves"]),
            engine_top8=engine_top8, static_top8=static_top8,
            top8_overlap=overlap, static_vs_engine=penalties,
        ))

    engine.close()

    # Report
    print("\n" + "=" * 60)
    print("CONSISTENCY ANALYSIS REPORT")
    print("=" * 60)

    overlaps = [s.top8_overlap for s in samples]
    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
    print(f"Avg overlap (top-8): {avg_overlap:.2f}/8 ({avg_overlap/8*100:.1f}%)")
    print(f"Engine data: {engine_ok_count}/{len(POSITIONS)}")

    # Calculate per-cell statistics
    total_static = 0
    total_in_engine = 0
    for s in samples:
        for cell in s.static_top8:
            total_static += 1
            r, c = cell
            for ms, pr, v in s.engine_top8:
                er, ec = gtp_to_rc(ms)
                if er == r and ec == c:
                    total_in_engine += 1
                    break
    hit_rate = total_in_engine / total_static if total_static else 0
    print(f"Static top-8 cells in engine top-8: {total_in_engine}/{total_static} ({hit_rate*100:.1f}%)")
    print(f"Avg engine prior for overlapping cells: will compute...")

    # Save
    output = {
        "summary": {
            "total_positions": len(POSITIONS),
            "engine_ok": engine_ok_count,
            "avg_overlap": round(avg_overlap, 2),
            "avg_overlap_rate": round(avg_overlap / 8, 4),
            "hit_rate": round(hit_rate, 4),
            "total_static_cells": total_static,
            "total_hit_cells": total_in_engine,
        },
        "positions": []
    }
    for s in samples:
        pos_out = {
            "position_id": s.position_id,
            "description": s.description,
            "moves_on_board": s.moves_on_board,
            "color": s.color, "count": s.count,
            "static_top8": [list(c) for c in s.static_top8],
            "top8_overlap": s.top8_overlap,
            "engine_top8": [
                {"move": ms, "prior": round(pr, 4), "visits": v}
                for ms, pr, v in s.engine_top8
            ],
            "static_vs_engine_penalty": [round(p, 4) for p in s.static_vs_engine],
        }
        output["positions"].append(pos_out)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
