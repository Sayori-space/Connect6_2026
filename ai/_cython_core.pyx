# cython: language_level=3, boundscheck=False, wraparound=False
"""
Cython 加速核心热循环。
"""

_SCORE = (0, 1, 10, 500, 30_000, 1_000_000, 100_000_000)


def cy_cell_val(int r, int c, int ci, list cw, list wcnt):
    """窗口基线估值 —— AlphaBetaAI._cell_val 的内层循环。"""
    cdef int oi = 1 - ci
    cdef int val = 0
    cdef int widx, our, opp
    cdef list wc
    cdef list windows = cw[r][c]

    for widx in windows:
        wc = wcnt[widx]
        our = wc[ci]
        opp = wc[oi]
        if opp == 0:
            val += _SCORE[our + 1] - _SCORE[our]
        elif our == 0:
            val += _SCORE[opp]
    return val


def cy_proximity_bonus(int r, int c, int our_color, list fg,
                       list prox_nbrs, int prox_bonus):
    """邻近对手棋子奖励。"""
    cdef int pos = r * 19 + c
    cdef int bonus = 0
    cdef int npos, stone

    for npos, _ in prox_nbrs[pos]:
        stone = fg[npos]
        if stone != 0 and stone != our_color:
            bonus += prox_bonus
    return bonus


def cy_place_update(int r, int c, int color,
                    list fg, list cc, list nbrs,
                    list cw, list wcnt, list escore,
                    list prox_nbrs, int prox_bonus,
                    list prox_score):
    """
    落子：更新 fg、cc、wcnt、escore、proximity_score。
    等价于 _place 的核心逻辑，但所有内层循环是 C 编译的。
    """
    cdef int N = 19
    cdef int pos = r * N + c
    cdef int ci = 0 if color == 1 else 1  # BLACK=1, WHITE=2

    # 更新 fg
    fg[pos] = color

    # 更新候选计数器
    cdef int n, np
    for n in nbrs[pos]:
        cc[n] += 1

    # 更新窗口计数和 escore
    cdef int widx, b, w
    cdef list wc
    cdef int e0 = escore[0]
    cdef int e1 = escore[1]

    for widx in cw[r][c]:
        wc = wcnt[widx]
        b = wc[0]
        w = wc[1]

        if b != 0 and w == 0:
            e0 -= _SCORE[b]
        if w != 0 and b == 0:
            e1 -= _SCORE[w]

        wc[ci] = wc[ci] + 1

        b = wc[0]
        w = wc[1]

        if b != 0 and w == 0:
            e0 += _SCORE[b]
        if w != 0 and b == 0:
            e1 += _SCORE[w]

    escore[0] = e0
    escore[1] = e1

    # 更新邻近分
    cdef int prox_inc = 0
    cdef int p_npos, p_stone
    if prox_bonus > 0:
        for p_npos, _ in prox_nbrs[pos]:
            p_stone = fg[p_npos]
            if p_stone != 0 and p_stone != color:
                prox_inc += prox_bonus
        prox_score[ci] = prox_score[ci] + prox_inc


def cy_remove_update(int r, int c, int color,
                     list fg, list cc, list nbrs,
                     list cw, list wcnt, list escore,
                     list prox_nbrs, int prox_bonus,
                     list prox_score):
    """
    提子：恢复 fg、cc、wcnt、escore、proximity_score。
    """
    cdef int N = 19
    cdef int pos = r * N + c
    cdef int ci = 0 if color == 1 else 1

    # 更新邻近分（在移除前计算，此时 stone 还在）
    cdef int prox_dec = 0
    cdef int r_npos, r_stone
    if prox_bonus > 0:
        for r_npos, _ in prox_nbrs[pos]:
            r_stone = fg[r_npos]
            if r_stone != 0 and r_stone != color:
                prox_dec += prox_bonus
        prox_score[ci] = prox_score[ci] - prox_dec

    # 恢复 fg
    fg[pos] = 0

    # 恢复候选计数器
    cdef int n
    for n in nbrs[pos]:
        cc[n] -= 1

    # 恢复窗口计数和 escore
    cdef int widx, b, w
    cdef list wc
    cdef int e0 = escore[0]
    cdef int e1 = escore[1]

    for widx in cw[r][c]:
        wc = wcnt[widx]
        b = wc[0]
        w = wc[1]

        if b != 0 and w == 0:
            e0 -= _SCORE[b]
        if w != 0 and b == 0:
            e1 -= _SCORE[w]

        wc[ci] = wc[ci] - 1

        b = wc[0]
        w = wc[1]

        if b != 0 and w == 0:
            e0 += _SCORE[b]
        if w != 0 and b == 0:
            e1 += _SCORE[w]

    escore[0] = e0
    escore[1] = e1
