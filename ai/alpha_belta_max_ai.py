"""
Alpha-Belta-Max Connect6 AI.

This is the pure alpha-beta/pruning route's stronger experimental branch.
It starts from AlphaBeltaPlusAI's tactical safeguards and keeps the class
separate so the baseline and plus versions remain available for comparison.
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
from utils.constants import BLACK, EMPTY


_RUN_SHAPE_BONUS = (0, 0, 1, 4, 12, 40, 120)
_OPEN_END_BONUS = (0, 1, 3)
_MAX_TOTAL_SHAPE_BONUS = 300
_MAX_HISTORY_SCORE = 50_000
_ASPIRATION_WINDOW = 250_000
_THREAT_PAIR_LIMIT = 10


class AlphaBeltaMaxAI(AlphaBeltaPlusAI):
    def __init__(self) -> None:
        super().__init__()
        self._history_score: Dict[Tuple[int, int], int] = {}
        self._killer_pairs: Dict[int, List[Tuple[Tuple[int, int], ...]]] = {}
        self._root_hint_pair: Optional[Tuple[Tuple[int, int], ...]] = None
        self._last_root_score: Optional[int] = None
        self._enable_root_aspiration = False
        self.last_decision: Dict[str, object] = {}

    @property
    def name(self) -> str:
        return "alpha-belta-max"

    def get_moves(self, board, color: int, count: int):
        self._history_score.clear()
        self._killer_pairs.clear()
        self._root_hint_pair = None
        self._last_root_score = None

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

        if len(self._tt) > 400_000:
            self._tt = {}

        think_time = getattr(self, "think_time_seconds", _THINK_TIME)
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

        forced = self._find_wins(cands, color, count)
        if forced:
            return self._moves_for_decision("immediate_win", forced, color, count)

        block = self._find_blocks(cands, color, count)
        if block:
            return self._moves_for_decision("immediate_block", block, color, count)

        multi_threat_block = self._find_multi_threat_blocks(cands, color, count)
        if multi_threat_block:
            return self._moves_for_decision(
                "multi_threat_block",
                multi_threat_block,
                color,
                count,
            )

        forcing_chain_block = self._find_forcing_threat_chain_blocks(
            cands,
            color,
            count,
        )
        if forcing_chain_block:
            return self._moves_for_decision(
                "forcing_chain_block",
                forcing_chain_block,
                color,
                count,
            )

        multi_threat = self._find_multi_threat_attack(cands, color, count)
        if multi_threat:
            return self._moves_for_decision(
                "multi_threat_attack",
                multi_threat,
                color,
                count,
            )

        forcing_chain = self._find_forcing_threat_chain_attack(cands, color, count)
        if forcing_chain:
            return self._moves_for_decision(
                "forcing_chain_attack",
                forcing_chain,
                color,
                count,
            )

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

    def _order_pairs_for_depth(
        self,
        pairs: List[Tuple[Tuple[int, int], ...]],
        depth: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        ordered = list(pairs)
        ordered.sort(
            key=lambda pair: (
                self._killer_rank(pair, depth),
                self._pair_history_score(pair),
            ),
            reverse=True,
        )
        return ordered

    def _order_root_pairs(
        self,
        pairs: List[Tuple[Tuple[int, int], ...]],
        depth: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        ordered = self._order_pairs_for_depth(pairs, depth)
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

    def _cell_val(self, r: int, c: int, ci: int) -> int:
        return super()._cell_val(r, c, ci) + self._shape_bonus(r, c, ci)

    def _winning_cells_after_pair(
        self,
        pair: Tuple[Tuple[int, int], ...],
        color: int,
        ci: int,
        limit: int,
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
    ) -> Optional[List[Tuple[int, int]]]:
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
            win_cells = self._winning_cells_after_pair(
                pair,
                color,
                ci,
                limit=target_wins,
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
    ) -> Optional[List[Tuple[int, int]]]:
        opp = _opp(color)
        threat_pair = self._find_multi_threat_attack(cands, opp, count)
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
    ) -> Optional[List[Tuple[int, int]]]:
        opp = _opp(color)
        threat_pair = self._find_forcing_threat_chain_attack(cands, opp, count)
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
    ) -> Optional[List[Tuple[int, int]]]:
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
            forced_replies = self._immediate_winning_cells_after_pair(
                pair,
                color,
                ci,
                limit=count + 1,
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

    def _gen_pairs(
        self,
        ranked: List[Tuple[int, int]],
        ci: int,
        count: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        pairs = super()._gen_pairs(ranked, ci, count)
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
        if hasattr(self, "last_search_stats"):
            self.last_search_stats["nodes"] += 1

        if time.monotonic() > deadline:
            return self._eval(0 if color == BLACK else 1)

        h = (self._hash, color)
        tt_entry = self._tt.get(h)
        tt_best: Optional[Tuple[Tuple[int, int], ...]] = None
        if tt_entry is not None:
            td, ts, tf, tt_best = tt_entry
            if td >= depth:
                if tf == _EXACT:
                    return ts
                if tf == _LOWER:
                    alpha = max(alpha, ts)
                elif tf == _UPPER:
                    beta = min(beta, ts)
                if alpha >= beta:
                    return ts

        ci = 0 if color == BLACK else 1

        if depth == 0:
            s = self._eval(ci)
            self._tt[h] = (0, s, _EXACT, None)
            return s

        cands = self._candidates()
        if not cands:
            return 0

        max_c = _MAX_CANDS[min(depth, len(_MAX_CANDS) - 1)]
        cands = self._sorted_cands(cands, ci, max_c)

        forced = self._find_wins(cands, color, 2)
        if forced:
            s = _WIN + depth
            self._tt[h] = (depth, s, _EXACT, tuple(forced))
            return s

        pairs = self._order_pairs_for_depth(self._gen_pairs(cands, ci, 2), depth)
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
                self._remember_killer(pair, depth)
                self._remember_pair(pair, depth)
                break

        if time.monotonic() <= deadline:
            flag = (
                _EXACT if orig_alpha < best < beta
                else (_LOWER if best >= beta else _UPPER)
            )
            self._tt[h] = (depth, best, flag, best_pair)

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

        max_c = _MAX_CANDS[min(depth + 1, len(_MAX_CANDS) - 1)]
        cands = self._sorted_cands(cands, ci, max_c)
        pairs = self._order_root_pairs(self._gen_pairs(cands, ci, count), depth)

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
