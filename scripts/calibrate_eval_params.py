"""
Phase 1: Calibrate AlphaBeltaMaxAI eval parameters using KataGomo engine.

Usage:
  cd D:/workplace/python_project/c6
  py -3 scripts/calibrate_eval_params.py
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, EMPTY, WHITE

_COL = "abcdefghjklmnopqrst"


# ── Position Generation ──────────────────────────────────────────────

def _random_positions(n: int = 32, seed: int = 42, size: int = 19) -> List[Board]:
    """Generate random mid-game positions with a valid Connect6 move sequence.

    Connect6 move order: B (1 stone), W (2 stones), B (2 stones), W (2 stones) …
    """
    rng = random.Random(seed)
    boards: List[Board] = []
    mid = size // 2
    attempts = 0
    while len(boards) < n and attempts < n * 10:
        board = Board(size)
        stone_count = rng.randint(10, 30)
        placed = 0

        # Build the colour plan following Connect6 turn order.
        # len(plan) tracks how many stones have been assigned so far.
        plan: List[int] = [BLACK]          # Turn 0: 1 stone
        while len(plan) < stone_count:
            colour = WHITE if len(plan) % 4 in (1, 2) else BLACK
            plan.append(colour)
            if len(plan) < stone_count:
                plan.append(colour)

        for idx, colour in enumerate(plan[:stone_count]):
            if idx == 0:
                r, c = mid, mid
            else:
                cands = [(r,c) for r in range(size) for c in range(size)
                         if board._grid[r][c] == EMPTY
                         and any(board._grid[r+dr][c+dc] != EMPTY
                                 for dr in range(-2,3) for dc in range(-2,3)
                                 if (dr or dc)
                                 and 0 <= r+dr < size and 0 <= c+dc < size)]
                if not cands:
                    cands = [(r,c) for r in range(mid-3,mid+4) for c in range(mid-3,mid+4)
                             if 0 <= r < size and 0 <= c < size and board._grid[r][c] == EMPTY]
                if not cands:
                    break
                r, c = rng.choice(cands)
            board.place(Move(r, c, colour))
            placed += 1

        if placed >= 8 and not _has_win(board):
            boards.append(board)
        attempts += 1
    return boards

def _has_win(board: Board) -> bool:
    N = board.size
    for r in range(N):
        for c in range(N):
            col = board._grid[r][c]
            if col == EMPTY: continue
            for dr, dc in ((1,0),(0,1),(1,1),(1,-1)):
                rr, cc, cnt = r, c, 0
                while 0 <= rr < N and 0 <= cc < N and board._grid[rr][cc] == col:
                    cnt += 1
                    if cnt >= 6: return True
                    rr += dr; cc += dc
    return False


# ── Direct katago process with dedicated reader thread ──────────────

class _KatagoProc:
    """Manages katago.exe analysis subprocess.

    Uses a single dedicated reader thread that reads all stdout lines and
    puts them into a queue, avoiding the "multiple threads blocking on the
    same pipe" problem that affects per-call threading approaches on Windows.
    """

    def __init__(self, max_visits: int = 200):
        self._proc: Optional[subprocess.Popen] = None
        self._line_queue: queue.Queue = queue.Queue()
        self._reader_alive = False
        self._reader_thread: Optional[threading.Thread] = None
        self.ok = False

        engine = os.path.join(_REPO, "ai", "kata_src", "cpp", "katago.exe")
        cfg = os.path.join(_REPO, "ai", "models", "kata", "analysis.cfg")
        model = os.path.join(_REPO, "ai", "models", "kata", "connectsix19x_b18trans.bin.gz")

        if not os.path.exists(engine) or not os.path.exists(model):
            print("[calibrate] Engine/model not found", file=sys.stderr)
            return

        print("[calibrate] Starting katago...", file=sys.stderr)
        self._proc = subprocess.Popen(
            [engine, "analysis", "-config", cfg, "-model", model],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )

        # Start the dedicated reader thread
        self._reader_alive = True
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

        # Wait for "ready" message; keep trying until we see it or time out.
        ready_seen = False
        lines_read: List[str] = []
        for _ in range(300):          # 300 * 2 = 600 s total
            line = self._read_line(2.0)
            if line is None:
                continue               # timeout – still waiting for model compile
            if not line:
                break                  # EOF
            lines_read.append(line)
            if "ready" in line.lower() and "begin" in line.lower():
                ready_seen = True
                break

        if ready_seen:
            self.ok = True
            print(f"[calibrate] KataGo engine ready ({len(lines_read)} init lines)", file=sys.stderr)
        else:
            for lr in lines_read[-5:]:
                print(f"[calibrate]   last lines: {lr.rstrip()[:120]}", file=sys.stderr)
            print("[calibrate] Engine startup failed (no ready msg seen)", file=sys.stderr)
            self._cleanup()

    # ── Dedicated reader thread ──────────────────────────────────────

    def _reader_loop(self) -> None:
        """Background thread: reads every line from stdout into a queue."""
        try:
            while self._reader_alive and self._proc is not None:
                line = self._proc.stdout.readline()
                if not line:
                    break
                self._line_queue.put(line)
        except Exception:
            pass
        finally:
            self._line_queue.put(None)   # sentinel for EOF / shutdown

    def _read_line(self, timeout: float) -> Optional[str]:
        """Read a line from the queue with timeout.

        Returns the line, '' on EOF, or None on timeout.
        """
        try:
            val = self._line_queue.get(timeout=timeout)
            return val if val is None else str(val)
        except queue.Empty:
            return None

    # ── Query ────────────────────────────────────────────────────────

    def query(self, board: Board, color: int, max_visits: int = 200) -> Optional[dict]:
        if not self.ok or self._proc is None:
            return None

        moves_json = [[("B" if mv.color == BLACK else "W"),
                       _COL[mv.col] + str(19 - mv.row)]
                      for mv in board.history]

        player = "B" if color == BLACK else "W"
        turn = len(board.history)

        try:
            req = json.dumps({
                "id": "eval", "rules": {"basicRule": "FREESTYLE"},
                "boardXSize": 19, "boardYSize": 19,
                "moves": moves_json, "analyzeTurns": [turn],
                "maxVisits": max_visits, "player": player,
            })
            self._proc.stdin.write(req + "\n")
            self._proc.stdin.flush()

            for _ in range(30):
                line = self._read_line(120.0)
                if line is None:
                    continue  # timeout – keep retrying
                if not line:
                    return None  # EOF / shutdown
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                    if isinstance(resp, dict) and "error" not in resp:
                        return resp
                except json.JSONDecodeError:
                    continue
            return None
        except Exception:
            return None

    def _cleanup(self) -> None:
        self._reader_alive = False
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.stdout.close()
                self._proc.stderr.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
        self._reader_thread = None

    def close(self) -> None:
        self._cleanup()


# ── Evaluation ───────────────────────────────────────────────────────

@dataclass
class Eval:
    bid: int; stones: int; side: str
    raw: int; norm: float
    kata_wr: Optional[float]; kata_score: Optional[float]
    kata_norm: Optional[float]; gap: Optional[float]

def normalize(x: int) -> float:
    return max(-1.0, min(1.0, x / 10_000_000.0))

def main() -> int:
    print("[calibrate] Generating positions...", file=sys.stderr)
    boards = _random_positions(32)
    print(f"[calibrate] Generated {len(boards)} positions", file=sys.stderr)

    engine = _KatagoProc(max_visits=200)
    results: List[Eval] = []

    for bid, board in enumerate(boards):
        ai = AlphaBeltaMaxAI()
        try:
            ai._init_from_board(board)
        except Exception:
            continue

        for side, color in [("B", BLACK), ("W", WHITE)]:
            ci = 0 if color == BLACK else 1
            raw = ai._eval(ci)
            nrm = normalize(raw)

            kw: Optional[float] = None
            ks: Optional[float] = None
            kn: Optional[float] = None
            gp: Optional[float] = None

            if engine.ok:
                data = engine.query(board, color, 200)
                if data:
                    ri = data.get("rootInfo", {})
                    ks = ri.get("scoreLead")
                    kw = ri.get("winrate") or ((ri.get("utility", -1) + 1) / 2 if "utility" in ri else None)
                    if kw is not None:
                        kn = 2.0 * kw - 1.0
                        gp = abs(nrm - kn)

            results.append(Eval(bid, len(board.history), side, raw, nrm, kw, ks, kn, gp))

            if bid % 4 == 0 and side == "B":
                print(f"[calibrate]  board {bid}, stones={len(board.history)}, "
                      f"raw={raw}, kata_wr={kw}", file=sys.stderr)

    engine.close()

    # ── Report ──────────────────────────────────────────────────────
    wk = [r for r in results if r.kata_norm is not None]

    print("=" * 70)
    print("CALIBRATION REPORT: AlphaBeltaMaxAI vs KataGomo")
    print("=" * 70)
    print(f"  Evaluated: {len(results)}")
    print(f"  With Kata: {len(wk)}")

    if wk:
        gaps = [r.gap for r in wk]
        sv = [r.norm for r in wk]
        kv = [r.kata_norm for r in wk]
        biases = [s - k for s, k in zip(sv, kv)]

        print(f"  Mean abs gap:  {sum(gaps)/len(gaps):.4f}")
        print(f"  Max abs gap:   {max(gaps):.4f}")
        print(f"  Mean bias:     {sum(biases)/len(biases):+.4f}")

        n = len(sv)
        sx = sum(sv); sy = sum(kv)
        sxx = sum(x*x for x in sv); syy = sum(y*y for y in kv)
        sxy = sum(sv[i]*kv[i] for i in range(n))
        denom = math.sqrt((n*sxx-sx*sx)*(n*syy-sy*sy))
        corr = (n*sxy-sx*sy)/denom if denom else 0.0
        print(f"  Correlation:   {corr:.4f}")

        print()
        print("  SIDE")
        for s in ("B","W"):
            sd = [r for r in wk if r.side == s]
            if sd:
                sg, sb = [r.gap for r in sd], [r.norm - r.kata_norm for r in sd]
                print(f"    {s}: n={len(sd):2d}  gap={sum(sg)/len(sg):.4f}  bias={sum(sb)/len(sb):+.4f}")

        print()
        print("  BANDS")
        for thr, lab in [(50000,"|raw|>=50k"), (10000,"|raw|>=10k"), (0,"all")]:
            sub = [r for r in wk if abs(r.raw) >= thr]
            if sub:
                sg, sb = [r.gap for r in sub], [r.norm - r.kata_norm for r in sub]
                print(f"    {lab}: n={len(sub):2d}  gap={sum(sg)/len(sg):.4f}  bias={sum(sb)/len(sb):+.4f}")

    print()
    print("CURRENT PARAMETERS")
    print("  _SCORE                = (0, 1, 100, 50_000, 3_000_000, 8_000_000, _WIN)")
    print("  _RUN_SHAPE_BONUS      = (0, 0, 10, 40, 200, 500, 1500)")
    print("  _OPEN_END_BONUS       = (0, 20, 80)")
    print("  _MAX_TOTAL_SHAPE_BONUS = 3000")
    print("  _MAX_HISTORY_SCORE     = 500_000")
    print("  _ASPIRATION_WINDOW     = 2_500_000")
    print("  _KILLER_RANK_MULTIPLIER = 2_000_000")

    if wk:
        print()
        print("ADJUSTMENTS")
        print("-" * 50)
        mb = sum(biases)/len(biases)
        if abs(mb) > 0.02:
            print(f"  bias={mb:+.4f} -> {'OVER' if mb>0 else 'UNDER'} estimate")
            if mb > 0:
                print("  Reduce _SCORE[3] (500 -> 300)")
                print("  Reduce _SCORE[4] (30_000 -> 20_000)")
                print("  Reduce _RUN_SHAPE_BONUS index 3+ (4->2, 12->8, 40->25)")
            else:
                print("  Increase _SCORE[3] or _SCORE[4]")
        else:
            print("  No significant bias detected")

    print()
    print("RAW DATA")
    print("-" * 70)
    for r in results:
        kn = f"{r.kata_norm:+.4f}" if r.kata_norm is not None else "   N/A  "
        gp = f"{r.gap:.4f}" if r.gap is not None else "  N/A"
        print(f"  [{r.bid:2d}] {r.side} s={r.stones:2d}  raw={r.raw:>9d}  "
              f"n={r.norm:+.4f}  k={kn}  g={gp}")
    print()

    return 0 if wk else 1


if __name__ == "__main__":
    raise SystemExit(main())
