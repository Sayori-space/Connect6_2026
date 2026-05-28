"""
Alpha-Belta-Plus Connect6 AI.

This engine is intentionally separate from ``AlphaBetaAI`` so the original
pruning AI remains available for direct comparison.  It reuses the original
incremental board representation and alpha-beta skeleton, then strengthens
the tactical layer around two-stone Connect6 turns.
"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Tuple

from ai.alpha_beta_ai import AlphaBetaAI, _WIN, _opp
from utils.constants import BLACK, EMPTY, WHITE


_TACTICAL_PAIR_LIMIT = 12
_CONTINUATION_CAND_LIMIT = 16
_CONTINUATION_SCORE_THRESHOLD = 300_000


class AlphaBeltaPlusAI(AlphaBetaAI):
    """Alpha-beta variant with stronger two-stone tactical handling."""

    @property
    def name(self) -> str:
        return "alpha-belta-plus"

    def _color_from_index(self, ci: int) -> int:
        return BLACK if ci == 0 else WHITE

    def _cell_val(self, r: int, c: int, ci: int) -> int:
        return super()._cell_val(r, c, ci)

    def _run_bonus(self, widx: int, r: int, c: int, ci: int) -> int:
        color = self._color_from_index(ci)
        best = 0
        run = 0
        for wr, wc in self._wins[widx]:
            occ = color if (wr, wc) == (r, c) else self._fg[wr * self._N + wc]
            if occ == color:
                run += 1
                best = max(best, run)
            else:
                run = 0
        return (0, 0, 40, 700, 18_000, 350_000, _WIN)[best]

    def _gen_pairs(
        self,
        ranked: List[Tuple[int, int]],
        ci: int,
        count: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        return super()._gen_pairs(ranked, ci, count)

    def _find_wins(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
    ) -> Optional[List[Tuple[int, int]]]:
        single = super()._find_wins(cands, color, count)
        if single and len(single) >= count:
            return single[:count]
        if count < 2:
            return single

        ci = 0 if color == BLACK else 1
        ranked = self._sorted_cands(
            cands,
            ci,
            min(len(cands), _TACTICAL_PAIR_LIMIT),
        )
        pair = self._find_pair_win(ranked, color, ci)
        if pair:
            return list(pair)
        return single

    def _find_pair_win(
        self,
        ranked: List[Tuple[int, int]],
        color: int,
        ci: int,
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        for i, (r1, c1) in enumerate(ranked):
            if self._fg[r1 * self._N + c1] != EMPTY:
                continue
            self._place(r1, c1, color)
            try:
                for r2, c2 in ranked[i + 1 :]:
                    if self._fg[r2 * self._N + c2] != EMPTY:
                        continue
                    self._place(r2, c2, color)
                    try:
                        if self._is_win(r2, c2, ci) or self._is_win(r1, c1, ci):
                            return ((r1, c1), (r2, c2))
                    finally:
                        self._remove(r2, c2, color)
            finally:
                self._remove(r1, c1, color)
        return None

    def _count_immediate_winning_cells(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        ci: int,
        limit: int = 4,
    ) -> int:
        wins = 0
        seen = set()
        for r, c in cands:
            if (r, c) in seen or self._fg[r * self._N + c] != EMPTY:
                continue
            seen.add((r, c))
            self._place(r, c, color)
            try:
                if self._is_win(r, c, ci):
                    wins += 1
                    if wins >= limit:
                        break
            finally:
                self._remove(r, c, color)
        return wins

    def _find_blocks(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
    ) -> Optional[List[Tuple[int, int]]]:
        single = super()._find_blocks(cands, color, count)
        if single:
            return single[:count]
        if count < 2:
            return None

        opp = _opp(color)
        ci_o = 0 if opp == BLACK else 1
        ci = 1 - ci_o
        ranked = self._sorted_cands(
            cands,
            ci_o,
            min(len(cands), _TACTICAL_PAIR_LIMIT),
        )

        threats = self._find_pair_threats(ranked, opp, ci_o)
        blocks = self._choose_blocks_for_pair_threats(threats, ci, count)
        if not blocks:
            return None
        if len(blocks) >= count:
            return blocks[:count]

        redundant = {cell for pair in threats for cell in pair}
        for r, c in self._sorted_cands(cands, ci, len(cands)):
            if (r, c) in blocks or (r, c) in redundant:
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

    def _choose_blocks_for_pair_threats(
        self,
        threats: List[Tuple[Tuple[int, int], Tuple[int, int]]],
        ci: int,
        count: int,
    ) -> Optional[List[Tuple[int, int]]]:
        if not threats or count <= 0:
            return None

        cells = sorted({cell for pair in threats for cell in pair})
        best_combo: Optional[Tuple[Tuple[int, int], ...]] = None
        best_key: Optional[Tuple[int, int, int, Tuple[Tuple[int, int], ...]]] = None

        for pick_count in range(1, min(count, len(cells)) + 1):
            for combo in combinations(cells, pick_count):
                combo_set = set(combo)
                covered = sum(1 for pair in threats if combo_set.intersection(pair))
                if covered != len(threats):
                    continue
                defensive_value = sum(self._cell_val(r, c, ci) for r, c in combo)
                key = (
                    covered,
                    defensive_value,
                    tuple((-r, -c) for r, c in reversed(combo)),
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_combo = combo
            if best_combo is not None:
                return list(best_combo)

        pick_count = min(count, len(cells))
        for combo in combinations(cells, pick_count):
            combo_set = set(combo)
            covered = sum(1 for pair in threats if combo_set.intersection(pair))
            defensive_value = sum(self._cell_val(r, c, ci) for r, c in combo)
            key = (
                covered,
                defensive_value,
                tuple((-r, -c) for r, c in reversed(combo)),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_combo = combo

        return list(best_combo) if best_combo else None

    def _find_pair_threats(
        self,
        ranked: List[Tuple[int, int]],
        color: int,
        ci: int,
    ) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        threats: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        for i, (r1, c1) in enumerate(ranked):
            if self._fg[r1 * self._N + c1] != EMPTY:
                continue
            self._place(r1, c1, color)
            try:
                for r2, c2 in ranked[i + 1 :]:
                    if self._fg[r2 * self._N + c2] != EMPTY:
                        continue
                    self._place(r2, c2, color)
                    try:
                        if self._is_win(r2, c2, ci) or self._is_win(r1, c1, ci):
                            threats.append(((r1, c1), (r2, c2)))
                    finally:
                        self._remove(r2, c2, color)
            finally:
                self._remove(r1, c1, color)
        return threats
