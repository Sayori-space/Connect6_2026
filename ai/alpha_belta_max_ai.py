"""
Alpha-Belta-Max 六子棋 AI。

这是纯 alpha-beta/剪枝路线的更强实验分支。
它以 AlphaBeltaPlusAI 的战术保护为起点，并保持独立类，便于和基线版、plus 版比较。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from ai.alpha_beta_ai import (
    _EXACT,
    _LOWER,
    _MAX_CANDS,
    _THINK_TIME,
    _UPPER,
    _WIN,
    _opp,
)
from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI
from models.move import Move
from utils.constants import BLACK, EMPTY, WHITE

try:
    from ai._cython_core import (
        cy_cell_val, cy_proximity_bonus, cy_place_update, cy_remove_update,
    )
    _HAS_CYTHON = True
except ImportError:
    _HAS_CYTHON = False


_RUN_SHAPE_BONUS = (0, 0, 1, 4, 12, 40, 120)
_OPEN_END_BONUS = (0, 2, 8)
_MAX_TOTAL_SHAPE_BONUS = 300
_MAX_HISTORY_SCORE = 50_000
_ASPIRATION_WINDOW = 250_000
_THREAT_PAIR_LIMIT = 10
_KILLER_RANK_MULTIPLIER = 200_000
_PROXIMITY_BONUS = 8
_PROXIMITY_DIST = 2


class AlphaBeltaMaxAI(AlphaBeltaPlusAI):
    enable_profiling: bool = False
    _own_max_cands: Tuple[int, ...] = (0, 15, 20, 24, 28, 28, 28, 28, 28)

    def __init__(self) -> None:
        super().__init__()
        self._history_score: Dict[Tuple[int, int], int] = {}
        self._killer_pairs: Dict[int, List[Tuple[Tuple[int, int], ...]]] = {}
        self._root_hint_pair: Optional[Tuple[Tuple[int, int], ...]] = None
        self._last_root_score: Optional[int] = None
        self._enable_root_aspiration = False
        self.last_decision: Dict[str, object] = {}
        self._profile: Dict[str, int] = {}
        self._profile_init()
        self._ranked_cache: Dict[Tuple[int, int], int] = {}
        self._bonus_cache: Dict[Tuple[int, int, int], int] = {}
        self._proximity_score: List[int] = [0, 0]
        self._prox_nbrs: List[List[Tuple[int, int]]] = self._build_prox_nbrs()
        self._proximity_precomputed: bool = False

    @property
    def name(self) -> str:
        return "alpha-belta-max"

    # ── Proximity-aware eval ────────────────────────────────────────────

    def _reset(self) -> None:
        super()._reset()
        self._proximity_score[0] = 0
        self._proximity_score[1] = 0

    def _proximity_delta(self, r: int, c: int, color: int) -> int:
        """Bonus for playing near opponent stones (used in _place/_remove)."""
        return self._proximity_bonus_at(r, c, color)

    def _place(self, r: int, c: int, color: int) -> None:
        if _HAS_CYTHON:
            from ai.alpha_beta_ai import _Z as _zobrist
            cy_place_update(r, c, color,
                            self._fg, self._cc, self._nbrs,
                            self._cw, self._wcnt, self._escore,
                            self._prox_nbrs, _PROXIMITY_BONUS,
                            self._proximity_score)
            self._hash ^= _zobrist[r][c][color]
        else:
            super()._place(r, c, color)
            self._proximity_score[0 if color == BLACK else 1] += (
                self._proximity_delta(r, c, color))

    def _remove(self, r: int, c: int, color: int) -> None:
        if _HAS_CYTHON:
            from ai.alpha_beta_ai import _Z as _zobrist
            cy_remove_update(r, c, color,
                             self._fg, self._cc, self._nbrs,
                             self._cw, self._wcnt, self._escore,
                             self._prox_nbrs, _PROXIMITY_BONUS,
                             self._proximity_score)
            self._hash ^= _zobrist[r][c][color]
        else:
            ci = 0 if color == BLACK else 1
            self._proximity_score[ci] -= self._proximity_delta(r, c, color)
            super()._remove(r, c, color)

    def _eval(self, ci: int) -> int:
        e = self._escore
        p = self._proximity_score
        return (e[ci] - e[1 - ci]) + (p[ci] - p[1 - ci])

    # ── Opening book ────────────────────────────────────────────────────

    def _opening_book(
        self, board, color: int, count: int
    ) -> Optional[List[Tuple[int, int]]]:
        N = board.size
        mid = N // 2
        history_len = len(board.history)
        if history_len == 0:
            return None

        if history_len == 1:
            first = board.history[0]
            if first.row == mid and first.col == mid and first.color == BLACK:
                return [(mid - 1, mid - 1), (mid + 1, mid + 1)]

        if history_len == 3 and color == BLACK:
            first = board.history[0]
            h1 = board.history[1]
            h2 = board.history[2]
            if (first.row == mid and first.col == mid and first.color == BLACK
                    and {(h1.row, h1.col), (h2.row, h2.col)} == {(mid - 1, mid - 1), (mid + 1, mid + 1)}):
                return [(mid - 1, mid + 1), (mid + 1, mid - 1)]

        # White's 3rd turn after Black's response to the diagonal opening
        if history_len == 5 and color == WHITE:
            first = board.history[0]
            h1 = board.history[1]
            h2 = board.history[2]
            h3 = board.history[3]
            h4 = board.history[4]

            if (first.row == mid and first.col == mid and first.color == BLACK
                    and {(h1.row, h1.col), (h2.row, h2.col)} == {(mid - 1, mid - 1), (mid + 1, mid + 1)}):
                black_set = {(h3.row, h3.col), (h4.row, h4.col)}

                # Black diagonal cross (8,10)+(10,8) -> White horizontal split (9,7)+(9,11)
                if black_set == {(mid - 1, mid + 1), (mid + 1, mid - 1)}:
                    return [(mid, mid - 2), (mid, mid + 2)]

                # Black vertical expansion (7,9)+(11,9) -> White vertical counter (8,9)+(10,9)
                if black_set == {(mid - 2, mid), (mid + 2, mid)}:
                    return [(mid - 1, mid), (mid + 1, mid)]

                # Black horizontal expansion (9,7)+(9,11) -> White horizontal counter (9,8)+(9,10)
                if black_set == {(mid, mid - 2), (mid, mid + 2)}:
                    return [(mid, mid - 1), (mid, mid + 1)]

                # Black diagonal extension (7,7)+(11,11) -> White horizontal (9,8)+(9,10)
                if black_set == {(mid - 2, mid - 2), (mid + 2, mid + 2)}:
                    return [(mid, mid - 1), (mid, mid + 1)]

                # Black split vertical (8,9)+(10,9) -> White horizontal split (9,7)+(9,11)
                if black_set == {(mid - 1, mid), (mid + 1, mid)}:
                    return [(mid, mid - 2), (mid, mid + 2)]

                # Black split horizontal (9,8)+(9,10) -> White horizontal split (9,7)+(9,11)
                if black_set == {(mid, mid - 1), (mid, mid + 1)}:
                    return [(mid, mid - 2), (mid, mid + 2)]

                # Black asymmetric (7,8)+(11,12) -> White cross (9,11)+(11,9)
                if black_set == {(mid - 2, mid - 1), (mid + 2, mid + 3)}:
                    return [(mid, mid + 2), (mid + 2, mid)]

                # Black asymmetric (8,7)+(10,13) -> White cross (9,11)+(11,9)
                if black_set == {(mid - 1, mid - 2), (mid + 1, mid + 4)}:
                    return [(mid, mid + 2), (mid + 2, mid)]

        # Black's 4th turn deeper lines
        if history_len == 7 and color == BLACK:
            first = board.history[0]
            h1 = board.history[1]
            h2 = board.history[2]
            h3 = board.history[3]
            h4 = board.history[4]
            h5 = board.history[5]
            h6 = board.history[6]

            if (first.row == mid and first.col == mid and first.color == BLACK
                    and {(h1.row, h1.col), (h2.row, h2.col)} == {(mid - 1, mid - 1), (mid + 1, mid + 1)}):
                b2_set = {(h3.row, h3.col), (h4.row, h4.col)}
                w3_set = {(h5.row, h5.col), (h6.row, h6.col)}

                # Diagonal cross + White horizontal -> Black opposite diagonal (7,11)+(11,7)
                if (b2_set == {(mid - 1, mid + 1), (mid + 1, mid - 1)}
                        and w3_set == {(mid, mid - 2), (mid, mid + 2)}):
                    return [(mid - 2, mid + 2), (mid + 2, mid - 2)]

                # Vertical + White vertical counter -> Black diagonal cross (8,10)+(10,8)
                if (b2_set == {(mid - 2, mid), (mid + 2, mid)}
                        and w3_set == {(mid - 1, mid), (mid + 1, mid)}):
                    return [(mid - 1, mid + 1), (mid + 1, mid - 1)]

        return None

    def _profile_init(self) -> None:
        self._profile = dict(
            candidate_count=0,
            candidate_after_limit=0,
            pair_count=0,
            quiescence_nodes=0,
            quiescence_triggers=0,
            tt_lookups=0,
            tt_hits=0,
            tt_cutoffs=0,
            negamax_calls=0,
            beta_cutoffs=0,
            eval_calls=0,
        )

    def _profile_flush(self) -> None:
        if self.enable_profiling and hasattr(self, "last_search_stats"):
            self.last_search_stats.update(self._profile)

    def estimate_urgency(self, board, color: int, count: int) -> float:
        if not board.history:
            return 1.0

        self._init_from_board(board)
        cands = self._candidates()
        if not cands:
            return 1.0

        deadline = time.monotonic() + 0.05
        if self._find_wins(cands, color, count, deadline=deadline):
            return 3.0
        if self._find_blocks(cands, color, count, deadline=deadline):
            return 3.0

        if count >= 2:
            if self._find_multi_threat_blocks(cands, color, count, deadline=deadline):
                return 2.75
            if self._find_forcing_threat_chain_blocks(
                cands,
                color,
                count,
                deadline=deadline,
            ):
                return 2.75
            if self._find_multi_threat_attack(cands, color, count, deadline=deadline):
                return 2.5
            if self._find_forcing_threat_chain_attack(
                cands,
                color,
                count,
                deadline=deadline,
            ):
                return 2.5

        if len(cands) >= 50:
            return 1.5
        return 1.0

    def get_moves(self, board, color: int, count: int):
        self._search_started_at = time.monotonic()
        self.last_search_stats = {
            "nodes": 0,
            "root_calls": 0,
            "completed_depth": 0,
            "elapsed_seconds": 0.0,
            "decision_reason": "",
            "tactical_pairs": 0,
        }
        if self.enable_profiling:
            self._profile_init()
        self._history_score.clear()
        self._killer_pairs.clear()
        self._root_hint_pair = None
        self._last_root_score = None
        self._ranked_cache.clear()

        N = board.size
        if not board.history:
            mid = N // 2
            return self._moves_for_decision(
                "opening_center",
                [(mid, mid)],
                color,
                count,
            )

        self._init_from_board(board)

        opening = self._opening_book(board, color, count)
        if opening is not None:
            return self._moves_for_decision(
                "opening_book", opening, color, count)

        if len(self._tt) > 400_000:
            self._tt = {}

        self._urgency = self.estimate_urgency(board, color, count)

        think_time = getattr(self, "think_time_seconds", _THINK_TIME)
        if "think_time_seconds" not in self.__dict__:
            if self._urgency < 1.5:
                think_time = 1.2
            elif self._urgency < 2.0:
                think_time = 1.8
        deadline = time.monotonic() + think_time
        ci = 0 if color == BLACK else 1

        cands = self._candidates()
        if not cands:
            mid = N // 2
            return self._moves_for_decision(
                "fallback_center",
                [(mid, mid)] * count,
                color,
                count,
            )

        forced = self._find_wins(cands, color, count, deadline=deadline)
        if forced:
            return self._moves_for_decision(
                "immediate_win",
                self._ensure_companions(forced, color, count, deadline),
                color, count)

        block = self._find_blocks(cands, color, count, deadline=deadline)
        if block:
            return self._moves_for_decision(
                "immediate_block",
                self._ensure_companions(block, color, count, deadline),
                color, count)

        has_patterns = (
            self._escore[0] >= 500 or self._escore[1] >= 500
        )
        if has_patterns:
            multi_threat_block = self._find_multi_threat_blocks(
                cands, color, count, deadline=deadline)
            if multi_threat_block:
                return self._moves_for_decision(
                    "multi_threat_block",
                    self._ensure_companions(multi_threat_block, color, count, deadline),
                    color, count)

            forcing_chain_block = self._find_forcing_threat_chain_blocks(
                cands, color, count, deadline=deadline)
            if forcing_chain_block:
                return self._moves_for_decision(
                    "forcing_chain_block",
                    self._ensure_companions(forcing_chain_block, color, count, deadline),
                    color, count)

            multi_threat = self._find_multi_threat_attack(
                cands, color, count, deadline=deadline)
            if multi_threat:
                return self._moves_for_decision(
                    "multi_threat_attack",
                    self._ensure_companions(multi_threat, color, count, deadline),
                    color, count)

            forcing_chain = self._find_forcing_threat_chain_attack(
                cands, color, count, deadline=deadline)
            if forcing_chain:
                return self._moves_for_decision(
                    "forcing_chain_attack",
                    self._ensure_companions(forcing_chain, color, count, deadline),
                    color, count)

        top = self._sorted_cands(cands, ci, count)
        best: List[Tuple[int, int]] = top[:count]
        searched = False

        for depth in range(1, 10):
            if time.monotonic() >= deadline:
                break
            result = self._root_search(color, count, depth, deadline)
            if result is not None:
                best = result[:count]
                searched = True
                self.last_search_stats["completed_depth"] = depth

        seen: set = set()
        out: List[Move] = []
        for r, c in best:
            if (r, c) not in seen:
                seen.add((r, c))
                out.append(Move(r, c, color))
        if len(out) < count:
            for pos in range(N * N):
                if len(out) == count:
                    break
                r, c = pos // N, pos % N
                if (r, c) not in seen and self._fg[pos] == EMPTY:
                    seen.add((r, c))
                    out.append(Move(r, c, color))
        return self._record_decision(
            "alpha_beta_search" if searched else "static_fallback",
            out[:count],
            color,
            count,
        )

    def _moves_for_decision(
        self,
        reason: str,
        cells: List[Tuple[int, int]],
        color: int,
        count: int,
    ) -> List[Move]:
        return self._record_decision(
            reason,
            [Move(r, c, color) for r, c in cells[:count]],
            color,
            count,
        )

    def _ensure_companions(
        self,
        cells: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: float,
    ) -> List[Tuple[int, int]]:
        if count < 2 or len(cells) != count:
            return cells
        improved = self._search_companions(cells, color, count, deadline)
        return improved if improved is not None else cells

    def _search_companions(
        self,
        cells: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: float,
    ) -> Optional[List[Tuple[int, int]]]:
        ci = 0 if color == BLACK else 1
        opp = _opp(color)
        ci_o = 0 if opp == BLACK else 1
        mandatory: List[Tuple[int, int]] = []
        for r, c in cells:
            self._place(r, c, color)
            won = self._is_win(r, c, ci)
            self._remove(r, c, color)
            if won:
                mandatory.append((r, c))
                continue
            self._place(r, c, opp)
            blocked = self._is_win(r, c, ci_o)
            self._remove(r, c, opp)
            if blocked:
                mandatory.append((r, c))
                continue

        if not mandatory or len(mandatory) >= count or time.monotonic() >= deadline:
            return None

        slots = count - len(mandatory)
        used = set(mandatory)
        cands = [(r, c) for r, c in self._candidates() if (r, c) not in used]
        ranked = self._sorted_cands(cands, ci, min(len(cands), 15))
        best_score = -10_000_000
        best_extra: List[Tuple[int, int]] = ranked[:slots]

        if slots == 1:
            for r, c in ranked:
                if time.monotonic() >= deadline:
                    break
                self._place(r, c, color)
                try:
                    sc = self._eval(ci)
                    if sc > best_score:
                        best_score = sc
                        best_extra = [(r, c)]
                finally:
                    self._remove(r, c, color)
        else:
            pairs = self._gen_pairs(ranked, ci, slots)
            for pair in pairs:
                if time.monotonic() >= deadline:
                    break
                placed = []
                for r, c in pair:
                    self._place(r, c, color)
                    placed.append((r, c))
                try:
                    sc = self._eval(ci)
                    if sc > best_score:
                        best_score = sc
                        best_extra = list(pair)
                finally:
                    for r, c in reversed(placed):
                        self._remove(r, c, color)

        return mandatory + best_extra

    def _record_decision(
        self,
        reason: str,
        moves: List[Move],
        color: int,
        count: int,
    ) -> List[Move]:
        self.last_decision = {
            "reason": reason,
            "moves": [(move.row, move.col) for move in moves],
            "color": color,
            "requested_count": count,
        }
        if hasattr(self, "last_search_stats"):
            self.last_search_stats["decision_reason"] = reason
            self.last_search_stats["elapsed_seconds"] = (
                time.monotonic() - self._search_started_at
            )
        self._profile_flush()
        return moves

    def _remember_pair(
        self,
        pair: Tuple[Tuple[int, int], ...],
        depth: int,
    ) -> None:
        bonus = max(1, depth * depth)
        for cell in pair:
            self._history_score[cell] = min(
                _MAX_HISTORY_SCORE,
                self._history_score.get(cell, 0) + bonus,
            )

    def _cell_history_score(self, r: int, c: int) -> int:
        return self._history_score.get((r, c), 0)

    def _pair_history_score(self, pair: Tuple[Tuple[int, int], ...]) -> int:
        return sum(self._cell_history_score(r, c) for r, c in pair)

    def _remember_killer(
        self,
        pair: Tuple[Tuple[int, int], ...],
        depth: int,
    ) -> None:
        killers = self._killer_pairs.setdefault(depth, [])
        if pair in killers:
            killers.remove(pair)
        killers.insert(0, pair)
        del killers[2:]

    def _killer_rank(self, pair: Tuple[Tuple[int, int], ...], depth: int) -> int:
        killers = self._killer_pairs.get(depth, [])
        if pair not in killers:
            return 0
        return len(killers) - killers.index(pair)

    def _pair_creates_win(
        self,
        pair: Tuple[Tuple[int, int], ...],
        color: int,
        ci: int,
    ) -> bool:
        placed: List[Tuple[int, int]] = []
        try:
            for r, c in pair:
                if self._fg[r * self._N + c] != EMPTY:
                    continue
                self._place(r, c, color)
                placed.append((r, c))
                if self._is_win(r, c, ci):
                    return True
            return False
        finally:
            for r, c in reversed(placed):
                self._remove(r, c, color)

    def _pair_blocks_immediate_win(
        self,
        pair: Tuple[Tuple[int, int], ...],
        color: int,
    ) -> bool:
        opp = _opp(color)
        ci_opp = 0 if opp == BLACK else 1
        for r, c in pair:
            if self._fg[r * self._N + c] != EMPTY:
                continue
            self._place(r, c, opp)
            try:
                if self._is_win(r, c, ci_opp):
                    return True
            finally:
                self._remove(r, c, opp)
        return False

    def _pair_order_score(
        self,
        pair: Tuple[Tuple[int, int], ...],
        depth: int,
        color: Optional[int] = None,
        ci: Optional[int] = None,
        root: bool = False,
    ) -> int:
        score = 0
        if color is not None and ci is not None:
            if self._pair_creates_win(pair, color, ci):
                score += 100_000_000
            if self._pair_blocks_immediate_win(pair, color):
                score += 50_000_000
            score += sum(self._cell_val(r, c, ci) for r, c in pair)
            score += self._pair_connectivity_bonus(pair)
        score += self._killer_rank(pair, depth) * _KILLER_RANK_MULTIPLIER
        score += self._pair_history_score(pair)
        if root and pair == self._root_hint_pair:
            score += 10_000_000
        return score

    def _order_pairs_for_depth(
        self,
        pairs: List[Tuple[Tuple[int, int], ...]],
        depth: int,
        color: Optional[int] = None,
        ci: Optional[int] = None,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        ordered = list(pairs)
        ordered.sort(
            key=lambda pair: self._pair_order_score(pair, depth, color, ci),
            reverse=True,
        )
        return ordered

    def _order_root_pairs(
        self,
        pairs: List[Tuple[Tuple[int, int], ...]],
        depth: int,
        color: Optional[int] = None,
        ci: Optional[int] = None,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        ordered = self._order_pairs_for_depth(pairs, depth, color, ci)
        if color is not None and ci is not None:
            ordered.sort(
                key=lambda pair: self._pair_order_score(
                    pair,
                    depth,
                    color,
                    ci,
                    root=True,
                ),
                reverse=True,
            )
            return ordered
        if self._root_hint_pair in ordered:
            ordered.remove(self._root_hint_pair)
            ordered.insert(0, self._root_hint_pair)
        return ordered

    def _root_bounds(self) -> Tuple[int, int, bool]:
        if self._last_root_score is None:
            return -_WIN * 2, _WIN * 2, False
        return (
            max(-_WIN * 2, self._last_root_score - _ASPIRATION_WINDOW),
            min(_WIN * 2, self._last_root_score + _ASPIRATION_WINDOW),
            True,
        )

    def _active_root_bounds(self) -> Tuple[int, int, bool]:
        if not self._enable_root_aspiration:
            return -_WIN * 2, _WIN * 2, False
        return self._root_bounds()

    def _needs_full_root_research(
        self,
        score: int,
        alpha: int,
        beta: int,
        used_aspiration: bool,
    ) -> bool:
        return used_aspiration and (score <= alpha or score >= beta)

    def _tt_key(
        self,
        color: int,
        mode: str = "main",
        count: int = 2,
    ) -> Tuple[int, int, str, int]:
        return (self._hash, color, mode, count)

    def _store_tt(
        self,
        key,
        depth: int,
        score: int,
        flag: int,
        best_pair,
    ) -> None:
        existing = self._tt.get(key)
        if existing is not None:
            existing_depth, _existing_score, existing_flag, _existing_best = existing
            if existing_depth > depth:
                return
            if existing_depth == depth and existing_flag == _EXACT and flag != _EXACT:
                return
        self._tt[key] = (depth, score, flag, best_pair)

    def _dynamic_max_cands(self, depth: int) -> int:
        """Scale candidate count by position complexity (fewer patterns → more candidates)."""
        base = self._own_max_cands[min(depth, len(self._own_max_cands) - 1)]
        if base == 0:
            return 0
        total = abs(self._escore[0]) + abs(self._escore[1])
        if total < 100:
            return base * 3
        if total < 1000:
            return int(base * 2)
        return base

    @staticmethod
    def _build_prox_nbrs() -> List[List[Tuple[int, int]]]:
        """Precompute Manhattan-distance <= _PROXIMITY_DIST neighbours per cell."""
        N = 19
        nbrs: List[List[Tuple[int, int]]] = []
        for r in range(N):
            for c in range(N):
                cell_nbrs: List[Tuple[int, int]] = []
                for dr in range(-_PROXIMITY_DIST, _PROXIMITY_DIST + 1):
                    for dc in range(-_PROXIMITY_DIST, _PROXIMITY_DIST + 1):
                        if dr == 0 and dc == 0:
                            continue
                        if abs(dr) + abs(dc) > _PROXIMITY_DIST:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < N and 0 <= nc < N:
                            cell_nbrs.append((nr * N + nc, abs(dr) + abs(dc)))
                nbrs.append(cell_nbrs)
        return nbrs

    def _proximity_bonus_at(self, r: int, c: int, our_color: int) -> int:
        """Bonus for cells near opponent stones (uniform within range)."""
        if _HAS_CYTHON:
            return cy_proximity_bonus(
                r, c, our_color, self._fg, self._prox_nbrs, _PROXIMITY_BONUS)
        fg = self._fg
        bonus = 0
        pos = r * self._N + c
        for npos, _dist in self._prox_nbrs[pos]:
            if fg[npos] not in (EMPTY, our_color):
                bonus += _PROXIMITY_BONUS
        return bonus

    def _pair_connectivity_bonus(self, pair: Tuple[Tuple[int, int], ...]) -> int:
        """Small bonus for pairs whose cells are close to each other."""
        if len(pair) < 2:
            return 0
        (r1, c1), (r2, c2) = pair
        dist = abs(r1 - r2) + abs(c1 - c2)
        if dist <= 2:
            return (3 - dist) * 4
        return 0

    def _cell_val(self, r: int, c: int, ci: int) -> int:
        cached = self._bonus_cache.get((r, c, ci))
        if cached is not None:
            return cached
        our_color = BLACK if ci == 0 else WHITE
        base = (
            cy_cell_val(r, c, ci, self._cw, self._wcnt)
            if _HAS_CYTHON else super()._cell_val(r, c, ci)
        )
        val = (
            base
            + self._shape_bonus(r, c, ci)
            + self._defensive_shape_bonus(r, c, ci)
            + self._jump_connection_bonus(r, c, ci)
            + self._double_threat_bonus(r, c, ci)
            + self._proximity_bonus_at(r, c, our_color)
        )
        self._bonus_cache[(r, c, ci)] = val
        return val

    def _double_threat_bonus(self, r: int, c: int, ci: int) -> int:
        near_win = 0
        for widx in self._cw[r][c]:
            if self._wcnt[widx][ci] == 4:
                near_win += 1
        if near_win >= 2:
            return 300_000 * near_win
        return 0

    def _winning_cells_after_pair(
        self,
        pair: Tuple[Tuple[int, int], ...],
        color: int,
        ci: int,
        limit: int,
        deadline: Optional[float] = None,
    ) -> int:
        placed: List[Tuple[int, int]] = []
        try:
            for r, c in pair:
                if self._fg[r * self._N + c] != EMPTY:
                    return 0
                self._place(r, c, color)
                placed.append((r, c))
            return self._count_immediate_winning_cells(
                self._candidates(),
                color,
                ci,
                limit=limit,
                deadline=deadline,
            )
        finally:
            for r, c in reversed(placed):
                self._remove(r, c, color)

    def _immediate_winning_cells_after_pair(
        self,
        pair: Tuple[Tuple[int, int], ...],
        color: int,
        ci: int,
        limit: int,
        deadline: Optional[float] = None,
    ) -> List[Tuple[int, int]]:
        placed: List[Tuple[int, int]] = []
        try:
            for r, c in pair:
                if self._fg[r * self._N + c] != EMPTY:
                    return []
                self._place(r, c, color)
                placed.append((r, c))

            wins: List[Tuple[int, int]] = []
            seen = set()
            for r, c in self._candidates():
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if (r, c) in seen or self._fg[r * self._N + c] != EMPTY:
                    continue
                seen.add((r, c))
                self._place(r, c, color)
                try:
                    if self._is_win(r, c, ci):
                        wins.append((r, c))
                        if len(wins) >= limit:
                            break
                finally:
                    self._remove(r, c, color)
            return wins
        finally:
            for r, c in reversed(placed):
                self._remove(r, c, color)

    def _find_multi_threat_attack(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: Optional[float] = None,
    ) -> Optional[List[Tuple[int, int]]]:
        if deadline is not None and time.monotonic() >= deadline:
            return None
        if count < 2:
            return None
        ci = 0 if color == BLACK else 1
        target_wins = count + 1
        ranked = self._sorted_cands(
            cands,
            ci,
            min(len(cands), _THREAT_PAIR_LIMIT),
        )
        pairs = self._gen_pairs(ranked, ci, count)
        best_pair: Optional[Tuple[Tuple[int, int], ...]] = None
        best_key: Optional[Tuple[int, int]] = None
        for pair in pairs:
            if deadline is not None and time.monotonic() >= deadline:
                return list(best_pair) if best_pair else None
            win_cells = self._winning_cells_after_pair(
                pair,
                color,
                ci,
                limit=target_wins,
                deadline=deadline,
            )
            if win_cells < target_wins:
                continue
            attack_value = sum(self._cell_val(r, c, ci) for r, c in pair)
            key = (win_cells, attack_value)
            if best_key is None or key > best_key:
                best_key = key
                best_pair = pair
        return list(best_pair) if best_pair else None

    def _find_multi_threat_blocks(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: Optional[float] = None,
    ) -> Optional[List[Tuple[int, int]]]:
        opp = _opp(color)
        threat_pair = self._find_multi_threat_attack(
            cands,
            opp,
            count,
            deadline=deadline,
        )
        if not threat_pair:
            return None

        ci = 0 if color == BLACK else 1
        block = self._best_single_pair_block(threat_pair, ci)
        return self._complete_defensive_turn([block], threat_pair, cands, ci, count)

    def _find_forcing_threat_chain_blocks(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: Optional[float] = None,
    ) -> Optional[List[Tuple[int, int]]]:
        opp = _opp(color)
        threat_pair = self._find_forcing_threat_chain_attack(
            cands,
            opp,
            count,
            deadline=deadline,
        )
        if not threat_pair:
            return None

        ci = 0 if color == BLACK else 1
        block = self._best_single_pair_block(threat_pair, ci)
        return self._complete_defensive_turn([block], threat_pair, cands, ci, count)

    def _best_single_pair_block(
        self,
        threat_pair: List[Tuple[int, int]],
        ci: int,
    ) -> Tuple[int, int]:
        return max(
            threat_pair,
            key=lambda cell: (self._cell_val(cell[0], cell[1], ci), -cell[0], -cell[1]),
        )

    def _complete_defensive_turn(
        self,
        blocks: List[Tuple[int, int]],
        redundant: List[Tuple[int, int]],
        cands: List[Tuple[int, int]],
        ci: int,
        count: int,
    ) -> List[Tuple[int, int]]:
        if len(blocks) >= count:
            return blocks[:count]

        redundant_set = set(redundant)
        for r, c in self._sorted_cands(cands, ci, len(cands)):
            if (r, c) in blocks or (r, c) in redundant_set:
                continue
            blocks.append((r, c))
            if len(blocks) == count:
                return blocks

        for r, c in self._sorted_cands(cands, ci, len(cands)):
            if (r, c) not in blocks:
                blocks.append((r, c))
            if len(blocks) == count:
                break
        return blocks[:count]

    def _find_forcing_threat_chain_attack(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
        deadline: Optional[float] = None,
    ) -> Optional[List[Tuple[int, int]]]:
        if deadline is not None and time.monotonic() >= deadline:
            return None
        if count < 2:
            return None

        ci = 0 if color == BLACK else 1
        opp = _opp(color)
        ci_opp = 0 if opp == BLACK else 1
        ranked = self._sorted_cands(
            cands,
            ci,
            min(len(cands), _THREAT_PAIR_LIMIT),
        )

        for pair in self._gen_pairs(ranked, ci, count):
            if deadline is not None and time.monotonic() >= deadline:
                return None
            forced_replies = self._immediate_winning_cells_after_pair(
                pair,
                color,
                ci,
                limit=count + 1,
                deadline=deadline,
            )
            if len(forced_replies) != count:
                continue

            placed: List[Tuple[int, int, int]] = []
            try:
                valid = True
                for r, c in pair:
                    if self._fg[r * self._N + c] != EMPTY:
                        valid = False
                        break
                    self._place(r, c, color)
                    placed.append((r, c, color))
                if not valid:
                    continue

                for r, c in forced_replies:
                    if self._fg[r * self._N + c] != EMPTY:
                        valid = False
                        break
                    self._place(r, c, opp)
                    placed.append((r, c, opp))
                if not valid:
                    continue

                follow_up = self._find_multi_threat_attack(
                    self._candidates(),
                    color,
                    count,
                )
                if follow_up:
                    return list(pair)
            finally:
                for r, c, stone_color in reversed(placed):
                    self._remove(r, c, stone_color)

        return None

    def _sorted_cands(
        self,
        cands: List[Tuple[int, int]],
        ci: int,
        limit: int,
    ) -> List[Tuple[int, int]]:
        self._bonus_cache.clear()
        oi = 1 - ci
        local_scores: Dict[Tuple[int, int], int] = {}
        result: List[Tuple[int, int]] = []
        for r, c in cands:
            sv = self._cell_val(r, c, ci) + self._cell_val(r, c, oi)
            local_scores[(r, c)] = sv
            result.append((-sv, r, c))
        result.sort()
        ranked = [(r, c) for _, r, c in result[:limit]]
        self._ranked_cache = {cell: local_scores[cell] for cell in ranked}
        return ranked

    def _gen_pairs(
        self,
        ranked: List[Tuple[int, int]],
        ci: int,
        count: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        if count == 1:
            return [((r, c),) for r, c in ranked]
        cache = getattr(self, "_ranked_cache", {})
        sv = [cache.get(cell, 0) for cell in ranked]
        n = len(ranked)
        raw: List[Tuple[int, Tuple[Tuple[int, int], Tuple[int, int]]]] = []
        for i in range(n):
            for j in range(i + 1, n):
                raw.append((-(sv[i] + sv[j]), (ranked[i], ranked[j])))
        raw.sort(key=lambda x: x[0])
        pairs = [p for _, p in raw]
        pairs.sort(key=self._pair_history_score, reverse=True)
        return pairs

    def _pvs_child_score(
        self,
        opp_color: int,
        child_depth: int,
        alpha: int,
        beta: int,
        deadline: float,
        is_first_child: bool,
    ) -> int:
        if is_first_child:
            return -self._negamax(opp_color, child_depth, -beta, -alpha, deadline)

        score = -self._negamax(
            opp_color,
            child_depth,
            -alpha - 1,
            -alpha,
            deadline,
        )
        if alpha < score < beta:
            score = -self._negamax(opp_color, child_depth, -beta, -alpha, deadline)
        return score

    def _negamax(
        self,
        color: int,
        depth: int,
        alpha: int,
        beta: int,
        deadline: float,
    ) -> int:
        if self.enable_profiling:
            self._profile["negamax_calls"] += 1
        if hasattr(self, "last_search_stats"):
            self.last_search_stats["nodes"] += 1

        if time.monotonic() > deadline:
            if self.enable_profiling:
                self._profile["eval_calls"] += 1
            return self._eval(0 if color == BLACK else 1)

        h = self._tt_key(color, mode="main", count=2)
        if self.enable_profiling:
            self._profile["tt_lookups"] += 1
        tt_entry = self._tt.get(h)
        tt_best: Optional[Tuple[Tuple[int, int], ...]] = None
        if tt_entry is not None:
            if self.enable_profiling:
                self._profile["tt_hits"] += 1
            td, ts, tf, tt_best = tt_entry
            if td >= depth:
                if tf == _EXACT:
                    return ts
                if tf == _LOWER:
                    alpha = max(alpha, ts)
                elif tf == _UPPER:
                    beta = min(beta, ts)
                if alpha >= beta:
                    if self.enable_profiling:
                        self._profile["tt_cutoffs"] += 1
                    return ts

        ci = 0 if color == BLACK else 1

        if depth == 0:
            if self.enable_profiling:
                self._profile["eval_calls"] += 1
            max_q = 2 if getattr(self, "_urgency", 1.0) > 2.0 else 1
            self._quiescence_node_count = 0
            s = self._threat_quiescence(color, alpha, beta, deadline, max_ply=max_q)
            self._store_tt(h, 0, s, _EXACT, None)
            return s

        cands = self._candidates()
        if not cands:
            return 0

        max_c = self._dynamic_max_cands(depth)
        if self.enable_profiling:
            self._profile["candidate_count"] += len(cands)
        cands = self._sorted_cands(cands, ci, max_c)
        if self.enable_profiling:
            self._profile["candidate_after_limit"] += len(cands)

        forced = self._find_wins(cands, color, 2, deadline=deadline)
        if forced:
            s = _WIN + depth
            self._store_tt(h, depth, s, _EXACT, tuple(forced))
            return s

        pairs = self._order_pairs_for_depth(
            self._gen_pairs(cands, ci, 2),
            depth,
            color=color,
            ci=ci,
        )
        if self.enable_profiling:
            self._profile["pair_count"] += len(pairs)
        opp = _opp(color)

        if tt_best is not None and tt_best in pairs:
            pairs.remove(tt_best)
            pairs.insert(0, tt_best)

        best = -_WIN * 2
        best_pair = pairs[0] if pairs else None
        orig_alpha = alpha

        for index, pair in enumerate(pairs):
            placed: List[Tuple[int, int]] = []
            won = False
            for r, c in pair:
                self._place(r, c, color)
                placed.append((r, c))
                if self._is_win(r, c, ci):
                    won = True
                    break

            score = (
                _WIN + depth
                if won
                else self._pvs_child_score(
                    opp,
                    depth - 1,
                    alpha,
                    beta,
                    deadline,
                    index == 0,
                )
            )

            for r, c in reversed(placed):
                self._remove(r, c, color)

            if score > best:
                best = score
                best_pair = pair
            alpha = max(alpha, score)
            if alpha >= beta:
                if self.enable_profiling:
                    self._profile["beta_cutoffs"] += 1
                self._remember_killer(pair, depth)
                self._remember_pair(pair, depth)
                break

        if time.monotonic() <= deadline:
            flag = (
                _EXACT if orig_alpha < best < beta
                else (_LOWER if best >= beta else _UPPER)
            )
            self._store_tt(h, depth, best, flag, best_pair)

        return best

    def _root_search(
        self,
        color: int,
        count: int,
        depth: int,
        deadline: float,
    ) -> Optional[List[Tuple[int, int]]]:
        ci = 0 if color == BLACK else 1
        opp = _opp(color)
        cands = self._candidates()
        if not cands:
            return None

        max_c = self._dynamic_max_cands(depth + 1)
        cands = self._sorted_cands(cands, ci, max_c)
        pairs = self._order_root_pairs(
            self._gen_pairs(cands, ci, count),
            depth,
            color=color,
            ci=ci,
        )

        alpha, beta, used_aspiration = self._active_root_bounds()
        best_pair, best_score = self._search_root_pairs(
            color,
            count,
            depth,
            deadline,
            pairs,
            alpha,
            beta,
        )
        if (
            best_pair is not None
            and self._needs_full_root_research(best_score, alpha, beta, used_aspiration)
            and time.monotonic() <= deadline
        ):
            best_pair, best_score = self._search_root_pairs(
                color,
                count,
                depth,
                deadline,
                pairs,
                -_WIN * 2,
                _WIN * 2,
            )

        if best_pair:
            self._remember_pair(best_pair, depth)
            self._root_hint_pair = best_pair
            self._last_root_score = best_score
        return list(best_pair[:count]) if best_pair else None

    def _search_root_pairs(
        self,
        color: int,
        count: int,
        depth: int,
        deadline: float,
        pairs: List[Tuple[Tuple[int, int], ...]],
        alpha: int,
        beta: int,
    ) -> Tuple[Optional[Tuple[Tuple[int, int], ...]], int]:
        ci = 0 if color == BLACK else 1
        opp = _opp(color)
        best_score = -_WIN * 2
        best_pair: Optional[Tuple[Tuple[int, int], ...]] = None

        for pair in pairs:
            if time.monotonic() > deadline:
                break

            placed: List[Tuple[int, int]] = []
            won = False
            for r, c in pair:
                self._place(r, c, color)
                placed.append((r, c))
                if self._is_win(r, c, ci):
                    won = True
                    break

            if won:
                for r, c in reversed(placed):
                    self._remove(r, c, color)
                winning_pair = tuple(placed[:count])
                return winning_pair, _WIN + depth

            score = -self._negamax(opp, depth - 1, -beta, -alpha, deadline)

            for r, c in reversed(placed):
                self._remove(r, c, color)

            if score > best_score or best_pair is None:
                best_score = score
                best_pair = pair
            alpha = max(alpha, score)

        return best_pair, best_score

    def _threat_quiescence(
        self,
        color: int,
        alpha: int,
        beta: int,
        deadline: float,
        ply: int = 0,
        max_ply: int = 1,
    ) -> int:
        if self.enable_profiling:
            self._profile["quiescence_nodes"] += 1
            if ply == 0:
                self._profile["quiescence_triggers"] += 1
        qc = getattr(self, "_quiescence_node_count", 0) + 1
        self._quiescence_node_count = qc
        if qc > 5000:
            return self._eval(0 if color == BLACK else 1)
        ci = 0 if color == BLACK else 1
        stand_pat = self._eval(ci)
        if self.enable_profiling and ply > 0:
            self._profile["eval_calls"] += 1
        if time.monotonic() >= deadline or ply >= max_ply:
            return stand_pat

        if abs(stand_pat) < 500:
            return stand_pat

        cands = self._candidates()
        if not cands:
            return stand_pat

        cands = self._sorted_cands(
            cands,
            ci,
            min(len(cands), _THREAT_PAIR_LIMIT),
        )

        tactic = self._find_wins(cands, color, 2, deadline=deadline)
        if tactic:
            return max(stand_pat, _WIN + max_ply - ply)

        tactic = self._find_blocks(cands, color, 2, deadline=deadline)
        if not tactic:
            tactic = self._find_multi_threat_attack(
                cands,
                color,
                2,
                deadline=deadline,
            )
        if not tactic:
            opp = _opp(color)
            opp_multi = self._find_multi_threat_attack(
                cands, opp, 2, deadline=deadline)
            if opp_multi:
                block_pair = self._find_multi_threat_blocks(
                    cands, color, 2, deadline=deadline)
                if block_pair:
                    tactic = block_pair
                else:
                    return min(stand_pat, -(_WIN - 5000 + max_ply - ply))
        if not tactic:
            return stand_pat

        opp = _opp(color)
        placed: List[Tuple[int, int]] = []
        try:
            for r, c in tactic[:2]:
                if self._fg[r * self._N + c] != EMPTY:
                    continue
                self._place(r, c, color)
                placed.append((r, c))
            if not placed:
                return stand_pat
            score = -self._threat_quiescence(
                opp,
                -beta,
                -alpha,
                deadline,
                ply=ply + 1,
                max_ply=max_ply,
            )
            return max(stand_pat, score)
        finally:
            for r, c in reversed(placed):
                self._remove(r, c, color)

    def _shape_bonus(self, r: int, c: int, ci: int) -> int:
        color = self._color_from_index(ci)
        bonus = 0
        for widx in self._cw[r][c]:
            cells = self._wins[widx]
            best_run, open_ends = self._best_run_in_window(cells, r, c, color)
            bonus += _RUN_SHAPE_BONUS[best_run] + _OPEN_END_BONUS[open_ends]
            if bonus >= _MAX_TOTAL_SHAPE_BONUS:
                return _MAX_TOTAL_SHAPE_BONUS
        return bonus

    def _defensive_shape_bonus(self, r: int, c: int, ci: int) -> int:
        return self._shape_bonus(r, c, 1 - ci) * 3 // 4

    def _jump_connection_bonus(self, r: int, c: int, ci: int) -> int:
        color = self._color_from_index(ci)
        best = 0
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            left = self._count_run_from(r - dr, c - dc, -dr, -dc, color)
            right = self._count_run_from(r + dr, c + dc, dr, dc, color)
            if left and right:
                best = max(best, left + right + 1)
        return (0, 0, 20, 80, 300, 1000, 3000)[min(best, 6)]

    def _count_run_from(
        self,
        r: int,
        c: int,
        dr: int,
        dc: int,
        color: int,
    ) -> int:
        run = 0
        while 0 <= r < self._N and 0 <= c < self._N:
            if self._fg[r * self._N + c] != color:
                break
            run += 1
            r += dr
            c += dc
        return run

    def _best_run_in_window(
        self,
        cells,
        cand_r: int,
        cand_c: int,
        color: int,
    ) -> tuple[int, int]:
        best_run = 0
        best_open_ends = 0
        run_start = 0
        run_len = 0

        for idx, (r, c) in enumerate(cells):
            occ = color if (r, c) == (cand_r, cand_c) else self._fg[r * self._N + c]
            if occ == color:
                if run_len == 0:
                    run_start = idx
                run_len += 1
                open_ends = self._open_ends(cells, run_start, idx, cand_r, cand_c)
                if run_len > best_run or (
                    run_len == best_run and open_ends > best_open_ends
                ):
                    best_run = run_len
                    best_open_ends = open_ends
            else:
                run_len = 0

        return best_run, best_open_ends

    def _open_ends(
        self,
        cells,
        start_idx: int,
        end_idx: int,
        cand_r: int,
        cand_c: int,
    ) -> int:
        dr = cells[1][0] - cells[0][0]
        dc = cells[1][1] - cells[0][1]
        open_ends = 0

        before_r = cells[start_idx][0] - dr
        before_c = cells[start_idx][1] - dc
        if self._is_shape_empty(before_r, before_c, cand_r, cand_c):
            open_ends += 1

        after_r = cells[end_idx][0] + dr
        after_c = cells[end_idx][1] + dc
        if self._is_shape_empty(after_r, after_c, cand_r, cand_c):
            open_ends += 1

        return open_ends

    def _is_shape_empty(
        self,
        r: int,
        c: int,
        cand_r: int,
        cand_c: int,
    ) -> bool:
        if not (0 <= r < self._N and 0 <= c < self._N):
            return False
        if (r, c) == (cand_r, cand_c):
            return False
        return self._fg[r * self._N + c] == EMPTY
