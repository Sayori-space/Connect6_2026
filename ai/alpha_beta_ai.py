"""
alpha_beta_ai.py – Connect6 α-β pruning engine with iterative deepening.

Key techniques
──────────────
• Incremental window scoring   O(≤24) per stone placed / removed
• Incremental candidate set    O(≤25) neighbour-counter per placement
• Zobrist transposition table  with depth / bound flags
• Iterative deepening          with a hard per-move time budget
• Fast pair ordering           per-cell static value (no placement needed)
• Immediate win / forced-block detection before tree search
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

from ai.base_ai import BaseAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, EMPTY, WHITE

# ── Tunables ──────────────────────────────────────────────────────────────

_WIN        = 10_000_000          # sentinel win score (must exceed any eval)
_THINK_TIME = 2.5                 # seconds budget per move
_CAND_R     = 2                   # neighbour radius for candidate generation

# Max candidates to consider per node, indexed by remaining depth
# (shallower nodes use fewer candidates → less branching at leaves)
_MAX_CANDS = (0, 10, 14, 17, 20, 20, 20, 20, 20)

# Score for n same-colour unblocked stones in a window of 6
_SCORE = (0, 1, 10, 500, 30_000, 1_000_000, _WIN)

# Transposition-table entry flags
_EXACT, _LOWER, _UPPER = 0, 1, 2

# ── Zobrist keys ──────────────────────────────────────────────────────────

_rng = random.Random(0xC6A1_BEEF)
_Z: List[List[List[int]]] = [          # [row][col][color (0/1/2)]
    [[_rng.getrandbits(64) for _ in range(3)] for _ in range(19)]
    for _ in range(19)
]


def _opp(c: int) -> int:
    return WHITE if c == BLACK else BLACK


# ── AI class ──────────────────────────────────────────────────────────────

class AlphaBetaAI(BaseAI):
    """
    Connect6 AI: Alpha-Beta pruning + iterative deepening.

    The internal state (_fg, _cc, _wcnt, _escore, _hash) is mutated
    in-place during the search and rebuilt from board.history at the
    start of each get_moves() call.
    """

    @property
    def name(self) -> str:
        return "剪枝AI"

    # ── Construction ──────────────────────────────────────────────────────

    def __init__(self) -> None:
        N = 19
        self._N = N

        # Window index ──────────────────────────────────────────────────
        # _wins[i]  = tuple of (r, c) cells in window i
        # _cw[r][c] = list of window indices that contain cell (r, c)
        self._wins: List[Tuple[Tuple[int, int], ...]] = []
        self._cw:   List[List[List[int]]] = [
            [[] for _ in range(N)] for _ in range(N)
        ]
        self._build_windows(N)

        # Precomputed flat-index neighbour lists (for candidate counter) ─
        # _nbrs[pos] = all flat-positions within _CAND_R of pos (excl. pos)
        self._nbrs: List[List[int]] = []
        for r in range(N):
            for c in range(N):
                nb: List[int] = []
                for dr in range(-_CAND_R, _CAND_R + 1):
                    for dc in range(-_CAND_R, _CAND_R + 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < N and 0 <= nc < N:
                            nb.append(nr * N + nc)
                self._nbrs.append(nb)

        nw = len(self._wins)

        # Search state ──────────────────────────────────────────────────
        self._fg:    List[int]       = [EMPTY] * (N * N)  # flat grid
        self._cc:    List[int]       = [0]     * (N * N)  # candidate count
        self._wcnt:  List[List[int]] = [[0, 0] for _ in range(nw)]
        self._escore: List[int]      = [0, 0]             # [black, white]
        self._hash:  int             = 0
        self._tt:    Dict[int, Tuple] = {}                 # transposition table

    def _build_windows(self, N: int) -> None:
        wins = self._wins
        cw   = self._cw

        def add(cells: List[Tuple[int, int]]) -> None:
            idx = len(wins)
            t = tuple(cells)
            wins.append(t)
            for r, c in t:
                cw[r][c].append(idx)

        for r in range(N):                    # horizontal
            for sc in range(N - 5):
                add([(r, sc + k) for k in range(6)])
        for c in range(N):                    # vertical
            for sr in range(N - 5):
                add([(sr + k, c) for k in range(6)])
        for sr in range(N - 5):              # diagonal ↘
            for sc in range(N - 5):
                add([(sr + k, sc + k) for k in range(6)])
        for sr in range(5, N):               # anti-diagonal ↗
            for sc in range(N - 5):
                add([(sr - k, sc + k) for k in range(6)])

    # ── State reset / replay ─────────────────────────────────────────────

    def _reset(self) -> None:
        N  = self._N
        fg = self._fg
        cc = self._cc
        for i in range(N * N):
            fg[i] = EMPTY
            cc[i] = 0
        for w in self._wcnt:
            w[0] = 0
            w[1] = 0
        self._escore[0] = 0
        self._escore[1] = 0
        self._hash = 0

    def _init_from_board(self, board: Board) -> None:
        self._reset()
        for mv in board.history:
            self._place(mv.row, mv.col, mv.color)

    # ── Stone placement / removal ─────────────────────────────────────────

    def _place(self, r: int, c: int, color: int) -> None:
        N    = self._N
        pos  = r * N + c
        ci   = 0 if color == BLACK else 1
        sc   = _SCORE
        fg   = self._fg
        cc   = self._cc
        wcnt = self._wcnt
        esc  = self._escore

        fg[pos]       = color
        self._hash   ^= _Z[r][c][color]

        for np in self._nbrs[pos]:
            cc[np] += 1

        for widx in self._cw[r][c]:
            wc = wcnt[widx]
            b, w = wc[0], wc[1]
            if b and not w:  esc[0] -= sc[b]
            if w and not b:  esc[1] -= sc[w]
            wc[ci] += 1
            b, w = wc[0], wc[1]
            if b and not w:  esc[0] += sc[b]
            if w and not b:  esc[1] += sc[w]

    def _remove(self, r: int, c: int, color: int) -> None:
        N    = self._N
        pos  = r * N + c
        ci   = 0 if color == BLACK else 1
        sc   = _SCORE
        fg   = self._fg
        cc   = self._cc
        wcnt = self._wcnt
        esc  = self._escore

        fg[pos]       = EMPTY
        self._hash   ^= _Z[r][c][color]

        for np in self._nbrs[pos]:
            cc[np] -= 1

        for widx in self._cw[r][c]:
            wc = wcnt[widx]
            b, w = wc[0], wc[1]
            if b and not w:  esc[0] -= sc[b]
            if w and not b:  esc[1] -= sc[w]
            wc[ci] -= 1
            b, w = wc[0], wc[1]
            if b and not w:  esc[0] += sc[b]
            if w and not b:  esc[1] += sc[w]

    # ── Win detection ─────────────────────────────────────────────────────

    def _is_win(self, r: int, c: int, ci: int) -> bool:
        """True if cell (r,c) participates in a complete 6-in-a-row."""
        for widx in self._cw[r][c]:
            if self._wcnt[widx][ci] == 6:
                return True
        return False

    # ── Evaluation ────────────────────────────────────────────────────────

    def _eval(self, ci: int) -> int:
        e = self._escore
        return e[ci] - e[1 - ci]

    # ── Candidate management ──────────────────────────────────────────────

    def _candidates(self) -> List[Tuple[int, int]]:
        """All empty cells adjacent (within _CAND_R) to at least one stone."""
        N   = self._N
        fg  = self._fg
        cc  = self._cc
        res: List[Tuple[int, int]] = []
        for pos in range(N * N):
            if fg[pos] == EMPTY and cc[pos]:
                res.append((pos // N, pos % N))
        return res

    def _cell_val(self, r: int, c: int, ci: int) -> int:
        """
        Approximate score-gain for placing colour-index ci at (r, c).
        Uses window counts directly — no board mutation needed.
        """
        oi  = 1 - ci
        sc  = _SCORE
        val = 0
        for widx in self._cw[r][c]:
            wc  = self._wcnt[widx]
            our = wc[ci]
            opp = wc[oi]
            if opp == 0:
                val += sc[our + 1] - sc[our]   # our gain
            elif our == 0:
                val += sc[opp]                  # blocking opponent
        return val

    def _sorted_cands(
        self,
        cands: List[Tuple[int, int]],
        ci: int,
        limit: int,
    ) -> List[Tuple[int, int]]:
        """Return up to `limit` candidates, highest combined value first."""
        oi = 1 - ci
        scored = [
            (-(self._cell_val(r, c, ci) + self._cell_val(r, c, oi)), r, c)
            for r, c in cands
        ]
        scored.sort()
        return [(r, c) for _, r, c in scored[:limit]]

    def _gen_pairs(
        self,
        ranked: List[Tuple[int, int]],
        ci: int,
        count: int,
    ) -> List[Tuple[Tuple[int, int], ...]]:
        """Generate all count-stone combinations, ordered best-first."""
        if count == 1:
            return [((r, c),) for r, c in ranked]

        oi  = 1 - ci
        sv  = [
            self._cell_val(r, c, ci) + self._cell_val(r, c, oi)
            for r, c in ranked
        ]
        n   = len(ranked)
        raw: List[Tuple[int, Tuple[Tuple[int, int], Tuple[int, int]]]] = []
        for i in range(n):
            for j in range(i + 1, n):
                raw.append((-(sv[i] + sv[j]), (ranked[i], ranked[j])))
        raw.sort(key=lambda x: x[0])
        return [p for _, p in raw]

    # ── Forced-move helpers ───────────────────────────────────────────────

    def _find_wins(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
    ) -> Optional[List[Tuple[int, int]]]:
        """Return a list of cells that win immediately, or None."""
        ci   = 0 if color == BLACK else 1
        wins: List[Tuple[int, int]] = []
        for r, c in cands:
            self._place(r, c, color)
            if self._is_win(r, c, ci):
                wins.append((r, c))
            self._remove(r, c, color)
            if len(wins) == count:
                return wins
        if not wins:
            return None
        # One winning cell but need two: pair it with the best safe cell
        r0, c0 = wins[0]
        rest = self._sorted_cands(
            [(r, c) for r, c in cands if (r, c) != (r0, c0)], ci, 1
        )
        if rest:
            return [(r0, c0), rest[0]]
        # Fallback: any other empty cell
        N = self._N
        for pos in range(N * N):
            if self._fg[pos] == EMPTY and (pos // N, pos % N) != (r0, c0):
                return [(r0, c0), (pos // N, pos % N)]
        return [(r0, c0)]  # nearly-full board edge case

    def _find_blocks(
        self,
        cands: List[Tuple[int, int]],
        color: int,
        count: int,
    ) -> Optional[List[Tuple[int, int]]]:
        """Return moves that block an opponent immediate win, or None."""
        opp   = _opp(color)
        ci_o  = 0 if opp == BLACK else 1
        ci    = 1 - ci_o
        owins: List[Tuple[int, int]] = []
        for r, c in cands:
            self._place(r, c, opp)
            if self._is_win(r, c, ci_o):
                owins.append((r, c))
            self._remove(r, c, opp)
        if not owins:
            return None
        if len(owins) >= count:
            return owins[:count]
        # One opponent win cell; block it and add best extra stone
        r0, c0 = owins[0]
        rest = self._sorted_cands(
            [(r, c) for r, c in cands if (r, c) != (r0, c0)], ci, 1
        )
        if rest:
            return [(r0, c0), rest[0]]
        N = self._N
        for pos in range(N * N):
            if self._fg[pos] == EMPTY and (pos // N, pos % N) != (r0, c0):
                return [(r0, c0), (pos // N, pos % N)]
        return [(r0, c0)]

    # ── Alpha-Beta (negamax form) ─────────────────────────────────────────

    def _negamax(
        self,
        color: int,
        depth: int,
        alpha: int,
        beta: int,
        deadline: float,
    ) -> int:
        if time.monotonic() > deadline:
            return self._eval(0 if color == BLACK else 1)

        # Transposition table lookup
        h        = self._hash
        tt_entry = self._tt.get(h)
        tt_best: Optional[Tuple] = None
        if tt_entry is not None:
            td, ts, tf, tt_best = tt_entry
            if td >= depth:
                if   tf == _EXACT: return ts
                elif tf == _LOWER: alpha = max(alpha, ts)
                elif tf == _UPPER: beta  = min(beta,  ts)
                if alpha >= beta:  return ts

        ci = 0 if color == BLACK else 1

        if depth == 0:
            s = self._eval(ci)
            self._tt[h] = (0, s, _EXACT, None)
            return s

        cands = self._candidates()
        if not cands:
            return 0   # no moves (shouldn't happen in normal play)

        # Limit candidates by depth
        max_c = _MAX_CANDS[min(depth, len(_MAX_CANDS) - 1)]
        cands = self._sorted_cands(cands, ci, max_c)

        # Immediate forced win inside search tree
        forced = self._find_wins(cands, color, 2)
        if forced:
            s = _WIN + depth
            self._tt[h] = (depth, s, _EXACT, tuple(forced))
            return s

        pairs  = self._gen_pairs(cands, ci, 2)
        opp    = _opp(color)

        # TT move-ordering hint: try the stored best move first
        if tt_best is not None and tt_best in pairs:
            pairs.remove(tt_best)
            pairs.insert(0, tt_best)

        best       = -_WIN * 2
        best_pair  = pairs[0] if pairs else None
        orig_alpha = alpha

        for pair in pairs:
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
                else -self._negamax(opp, depth - 1, -beta, -alpha, deadline)
            )

            for r, c in reversed(placed):
                self._remove(r, c, color)

            if score > best:
                best      = score
                best_pair = pair
            alpha = max(alpha, score)
            if alpha >= beta:
                break   # beta cut-off

        # Store to TT
        if time.monotonic() <= deadline:
            flag = (
                _EXACT if orig_alpha < best < beta
                else (_LOWER if best >= beta else _UPPER)
            )
            self._tt[h] = (depth, best, flag, best_pair)

        return best

    # ── Root search (one iteration of iterative deepening) ───────────────

    def _root_search(
        self,
        color: int,
        count: int,
        depth: int,
        deadline: float,
    ) -> Optional[List[Tuple[int, int]]]:
        """
        Alpha-beta at the root for a given depth.
        Returns the best move list (count cells) or None on timeout.
        """
        ci    = 0 if color == BLACK else 1
        opp   = _opp(color)
        cands = self._candidates()
        if not cands:
            return None

        max_c = _MAX_CANDS[min(depth + 1, len(_MAX_CANDS) - 1)]
        cands = self._sorted_cands(cands, ci, max_c)
        pairs = self._gen_pairs(cands, ci, count)

        best_score                    = -_WIN * 2
        best_pair: Optional[Tuple]    = None
        alpha, beta                   = -_WIN * 2, _WIN * 2

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
                return list(placed[:count])   # immediate win found

            score = -self._negamax(opp, depth - 1, -beta, -alpha, deadline)

            for r, c in reversed(placed):
                self._remove(r, c, color)

            if score > best_score or best_pair is None:
                best_score = score
                best_pair  = pair
            alpha = max(alpha, score)

        return list(best_pair[:count]) if best_pair else None

    # ── Public API ────────────────────────────────────────────────────────

    def get_moves(self, board: Board, color: int, count: int) -> List[Move]:
        N = board.size

        # First stone of the game → centre
        if not board.history:
            mid = N // 2
            return [Move(mid, mid, color)]

        self._init_from_board(board)

        # Bound TT memory
        if len(self._tt) > 400_000:
            self._tt = {}

        think_time = getattr(self, "think_time_seconds", _THINK_TIME)
        deadline = time.monotonic() + think_time
        ci       = 0 if color == BLACK else 1

        cands = self._candidates()
        if not cands:
            mid = N // 2
            return [Move(mid, mid, color)] * count

        # Pre-search: forced win or forced block
        forced = self._find_wins(cands, color, count)
        if forced:
            return [Move(r, c, color) for r, c in forced[:count]]

        block = self._find_blocks(cands, color, count)
        if block:
            return [Move(r, c, color) for r, c in block[:count]]

        # Greedy depth-0 fallback (in case depth-1 times out)
        top  = self._sorted_cands(cands, ci, count)
        best: List[Tuple[int, int]] = top[:count]

        # Iterative deepening
        for depth in range(1, 10):
            if time.monotonic() >= deadline:
                break
            result = self._root_search(color, count, depth, deadline)
            if result is not None:
                best = result[:count]

        # Ensure we always return exactly `count` distinct valid moves
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
        return out[:count]
