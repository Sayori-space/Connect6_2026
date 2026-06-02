"""
KataGomo 六子棋 AI — 引擎 MCTS 直出模式。

通过 subprocess 调用 katago.exe analysis 模式，
直接使用引擎的 MCTS + NN 搜索结果走子。
引擎不可用时退化为 AlphaBeltaMaxAI（保留全部优化）。
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, List, Optional, Tuple

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from models.move import Move
from utils.constants import BLACK, WHITE

_COL_LABELS = "abcdefghjklmnopqrst"
_MAX_VISITS = 800


class KataGomoAI(AlphaBeltaMaxAI):
    """KataGomo 引擎 MCTS 直出 AI。"""

    def __init__(
        self,
        engine_path: Optional[str] = None,
        model_path: Optional[str] = None,
        max_visits: int = _MAX_VISITS,
    ) -> None:
        super().__init__()
        self._process: Optional[subprocess.Popen] = None
        self._engine_ok = False
        self._max_visits = max_visits

        self._init_engine(engine_path, model_path)

    # ── 初始化 ─────────────────────────────────────────────────────

    def _init_engine(self, engine_path: Optional[str], model_path: Optional[str]) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if engine_path is None:
            engine_path = os.path.join(
                project_root, "ai", "kata_src", "cpp", "katago.exe")

        if model_path is None:
            model_path = os.path.join(
                project_root, "ai", "models", "kata",
                "connectsix19x_b18trans.bin.gz")

        config_path = os.path.join(
            project_root, "ai", "models", "kata", "analysis.cfg")
        self._write_config(config_path)

        if not os.path.exists(engine_path) or not os.path.exists(model_path):
            print("[KataGomo] Engine or model not found, fallback to AlphaBeltaMax")
            return

        try:
            self._process = subprocess.Popen(
                [engine_path, "analysis", "-config", config_path,
                 "-model", model_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for _ in range(200):
                line = self._process.stdout.readline()
                if not line:
                    break
                if "ready" in line.lower() and "begin" in line.lower():
                    self._engine_ok = True
                    print(f"[KataGomo] Ready (maxVisits={self._max_visits})")
                    break
            if not self._engine_ok:
                print("[KataGomo] Engine startup failed, fallback")
        except Exception as e:
            print(f"[KataGomo] Engine error: {e}, fallback")

    @staticmethod
    def _write_config(path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("logDir = analysis_logs\n")
            f.write("logToStderr = false\n")
            f.write("numAnalysisThreads = 1\n")
            f.write("numSearchThreads = 1\n")
            f.write("nnMaxBatchSize = 1\n")
            f.write("nnCacheSizePowerOfTwo = 18\n")

    @property
    def name(self) -> str:
        return "KataGomo" if self._engine_ok else "KataGomo(降级)"

    # ── 引擎查询 ─────────────────────────────────────────────────

    def _query_engine(
        self, board, color: int, count: int
    ) -> Optional[List[Tuple[int, int]]]:
        if not self._engine_ok or self._process is None:
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
                "id": "move",
                "rules": {"basicRule": "FREESTYLE"},
                "boardXSize": 19,
                "boardYSize": 19,
                "moves": moves_json,
                "analyzeTurns": [turn],
                "maxVisits": self._max_visits,
                "player": player,
            })
            self._process.stdin.write(request + "\n")
            self._process.stdin.flush()

            response = json.loads(self._process.stdout.readline())
            if "error" in response:
                return None

            move_infos = response.get("moveInfos", [])
            if not move_infos:
                return None

            selected: List[Tuple[int, int]] = []
            seen = set()
            for mi in move_infos:
                move_str = mi.get("move", "")
                if not move_str:
                    continue
                r, c = self._gtp_to_rc(move_str)
                if 0 <= r < 19 and 0 <= c < 19 and (r, c) not in seen:
                    seen.add((r, c))
                    selected.append((r, c))
                    if len(selected) >= count:
                        break

            return selected if len(selected) >= count else None
        except Exception:
            return None

    @staticmethod
    def _gtp_to_rc(move_str: str) -> Tuple[int, int]:
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

    # ── 主入口 ───────────────────────────────────────────────────

    def get_moves(self, board, color: int, count: int):
        if self._engine_ok:
            result = self._query_engine(board, color, count)
            if result is not None:
                return self._record_decision(
                    "kata_mcts",
                    [Move(r, c, color) for r, c in result[:count]],
                    color, count,
                )

        return super().get_moves(board, color, count)

    def __del__(self):
        if self._process is not None:
            try:
                self._process.stdin.close()
                self._process.stdout.close()
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                pass
