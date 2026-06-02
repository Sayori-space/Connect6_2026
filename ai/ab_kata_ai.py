"""
AB-Kata 六子棋 AI。

Alpha-Beta 搜索 + KataGo 分析引擎评估融合。
通过 subprocess 调用 katago.exe analysis 模式，
传 JSON 棋盘状态，收 value + policy 结果。
无引擎/模型时退化为 AlphaBeltaMaxAI。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Dict, List, Optional, Tuple

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from models.move import Move
from utils.constants import BLACK, WHITE, EMPTY

_NN_EVAL_WEIGHT = 0.30
_NN_POLICY_BOOST = 800_000
_MAX_CACHE = 50_000
_COL_LABELS = "abcdefghjklmnopqrst"


class ABKataAI(AlphaBeltaMaxAI):
    """Alpha-Beta + KataGo 分析引擎评估的混合 AI。"""

    def __init__(
        self,
        engine_path: Optional[str] = None,
        model_path: Optional[str] = None,
        max_visits: int = 25,
    ) -> None:
        super().__init__()
        self._process: Optional[subprocess.Popen] = None
        self._model_loaded = False
        self._cache: Dict[int, Tuple[float, List[float]]] = {}
        self._hits = 0
        self._misses = 0
        self._max_visits = max_visits
        self._search_color = BLACK
        self._move_history: List[str] = []
        self._nn_root_value: Optional[float] = None
        self._nn_root_policy: Optional[List[float]] = None
        self._root_static_eval: int = 0

        self._init(engine_path, model_path)

    # ── 初始化 ────────────────────────────────────────────────────────

    def _init(self, engine_path: Optional[str], model_path: Optional[str]) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if engine_path is None:
            candidates = [
                os.path.join(project_root, "ai", "kata_src", "cpp", "katago.exe"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    engine_path = c
                    break

        if model_path is None:
            candidates = [
                os.path.join(project_root, "ai", "models", "kata",
                             "connectsix19x_b18trans.bin.gz"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    model_path = c
                    break

        config_path = os.path.join(project_root, "ai", "models", "kata", "analysis.cfg")
        self._write_analysis_config(config_path, model_path or "")

        if engine_path and os.path.exists(engine_path) and model_path and os.path.exists(model_path):
            try:
                self._process = subprocess.Popen(
                    [
                        engine_path, "analysis",
                        "-config", config_path,
                        "-model", model_path,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for _ in range(80):
                    line = self._process.stdout.readline()
                    if not line:
                        break
                    if "ready" in line.lower() and "begin" in line.lower():
                        self._model_loaded = True
                        print(f"[AB-Kata] Engine started (maxVisits={self._max_visits})")
                        break
                if not self._model_loaded:
                    print("[AB-Kata] Engine did not send ready signal")
            except Exception as e:
                print(f"[AB-Kata] Engine start failed: {e}")

        if not self._model_loaded:
            print("[AB-Kata] Engine not available, using static eval")

    def _write_analysis_config(self, path: str, model_path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("logDir = analysis_logs\n")
            f.write("logToStderr = false\n")
            f.write("logAllGTPCommunication = false\n")
            f.write("logSearchInfo = false\n")
            f.write("numAnalysisThreads = 1\n")
            f.write("numSearchThreads = 1\n")
            f.write("nnMaxBatchSize = 1\n")
            f.write("nnCacheSizePowerOfTwo = 18\n")

    @property
    def name(self) -> str:
        return "AB-Kata" if self._model_loaded else "AB-Kata(无模型)"

    # ── 分析引擎通信 ────────────────────────────────────────────────

    def _analysis_query(
        self, color: int
    ) -> Optional[Tuple[float, List[float]]]:
        if self._process is None or self._process.poll() is not None:
            return None

        h = self._hash
        if h in self._cache:
            self._hits += 1
            return self._cache[h]
        self._misses += 1

        try:
            moves_json = json.dumps(self._move_history)
            player = "B" if color == BLACK else "W"
            request = json.dumps({
                "id": str(h),
                "rules": {"basicRule": "FREESTYLE"},
                "boardXSize": self._N,
                "boardYSize": self._N,
                "moves": json.loads(moves_json),
                "analyzeTurns": [len(self._move_history)],
                "maxVisits": self._max_visits,
                "player": player,
            })
            self._process.stdin.write(request + "\n")
            self._process.stdin.flush()

            response_line = self._process.stdout.readline()
            response = json.loads(response_line)

            root = response.get("rootInfo", {})
            wr = root.get("winrate", 0.5)
            value = wr * 2.0 - 1.0

            N = self._N
            policy = [0.0] * (N * N)
            for mi in response.get("moveInfos", []):
                move_str = mi.get("move", "")
                prior = mi.get("prior", 0.0)
                r, c = self._gtp_to_rc(move_str)
                if 0 <= r < N and 0 <= c < N:
                    policy[r * N + c] = prior

            if len(self._cache) >= _MAX_CACHE:
                self._cache.clear()
            self._cache[h] = (value, policy)
            return value, policy
        except Exception:
            return None

    def _gtp_to_rc(self, move_str: str) -> Tuple[int, int]:
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

    def _sync_moves(self, board) -> None:
        self._move_history = []
        for mv in board.history:
            col = _COL_LABELS[mv.col]
            row = str(19 - mv.row)
            stone = "B" if mv.color == BLACK else "W"
            self._move_history.append([stone, col + row])

    # ── 评估覆写 ─────────────────────────────────────────────────────

    def _eval(self, ci: int) -> int:
        base = super()._eval(ci)
        if not self._model_loaded or self._nn_root_value is None:
            return base
        ci_factor = 1 if ci == 0 else -1
        nn_adjustment = int(
            (self._nn_root_value * 500_000 * ci_factor - self._root_static_eval)
            * _NN_EVAL_WEIGHT
        )
        return base + nn_adjustment

    def _sorted_cands(
        self, cands: List[Tuple[int, int]], ci: int, limit: int
    ) -> List[Tuple[int, int]]:
        base_limit = max(limit, len(cands))
        ranked = super()._sorted_cands(cands, ci, base_limit)
        if not self._model_loaded or self._nn_root_policy is None:
            return ranked[:limit]
        N = self._N
        policy = self._nn_root_policy
        scored = []
        for r, c in ranked:
            base_val = self._cell_val(r, c, ci) + self._cell_val(r, c, 1 - ci)
            pi_val = policy[r * N + c] if r * N + c < len(policy) else 0.0
            boosted = base_val + int(pi_val * _NN_POLICY_BOOST)
            scored.append((-boosted, r, c))
        scored.sort()
        result = [(r, c) for _, r, c in scored[:limit]]
        self._ranked_cache = {
            cell: self._cell_val(cell[0], cell[1], ci) + self._cell_val(cell[0], cell[1], 1 - ci)
            + int((policy[cell[0] * N + cell[1]] if cell[0] * N + cell[1] < len(policy) else 0.0)
                  * _NN_POLICY_BOOST)
            for cell in result
        }
        return result

    def _pair_order_score(
        self,
        pair: Tuple[Tuple[int, int], ...],
        depth: int,
        color: Optional[int] = None,
        ci: Optional[int] = None,
        root: bool = False,
    ) -> int:
        score = super()._pair_order_score(pair, depth, color, ci, root)
        if self._model_loaded and self._nn_root_policy is not None and ci is not None:
            N = self._N
            policy = self._nn_root_policy
            for r, c in pair:
                idx = r * N + c
                if idx < len(policy):
                    score += int(policy[idx] * _NN_POLICY_BOOST)
        return score

    # ── 公共 API ─────────────────────────────────────────────────────

    def get_moves(self, board, color: int, count: int):
        self._nn_root_value = None
        self._nn_root_policy = None
        self._root_static_eval = 0
        self._search_color = color

        if self._model_loaded:
            self._sync_moves(board)
            result = self._analysis_query(color)
            if result is not None:
                self._nn_root_value, self._nn_root_policy = result
                ci = 0 if color == BLACK else 1
                self._root_static_eval = super()._eval(ci)

        urgency = self.estimate_urgency(board, color, count)
        if urgency < 1.5:
            self.think_time_seconds = 1.2
        elif urgency < 2.0:
            self.think_time_seconds = 1.8
        else:
            self.think_time_seconds = 2.5

        moves = super().get_moves(board, color, count)
        return moves

    def estimate_urgency(self, board, color: int, count: int) -> float:
        return super().estimate_urgency(board, color, count)

    def __del__(self):
        if self._process is not None:
            try:
                self._process.stdin.close()
                self._process.stdout.close()
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                pass
