import unittest

from ai.alpha_belta_max_ai import AlphaBeltaMaxAI
from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE


class AlphaBeltaMaxAITests(unittest.TestCase):
    def test_keeps_distinct_engine_name(self):
        self.assertEqual(AlphaBeltaMaxAI().name, "alpha-belta-max")

    def test_adds_shape_value_above_plus_for_open_run_extension(self):
        board = Board(19)
        for col in (6, 7, 8):
            self.assertTrue(board.place(Move(9, col, BLACK)))

        plus = AlphaBeltaPlusAI()
        max_ai = AlphaBeltaMaxAI()
        plus._init_from_board(board)
        max_ai._init_from_board(board)

        plus_score = plus._cell_val(9, 9, 0)
        max_score = max_ai._cell_val(9, 9, 0)

        self.assertGreater(max_score, plus_score)

    def test_shape_bonus_prefers_continuous_run_over_scattered_stones(self):
        continuous = Board(19)
        for col in (6, 7, 8):
            self.assertTrue(continuous.place(Move(9, col, BLACK)))

        scattered = Board(19)
        for col in (4, 6, 8):
            self.assertTrue(scattered.place(Move(9, col, BLACK)))

        continuous_bonus = self._max_extra_score(continuous, 9, 9)
        scattered_bonus = self._max_extra_score(scattered, 9, 9)

        self.assertGreater(continuous_bonus, scattered_bonus)

    def test_remembered_pair_is_ordered_first(self):
        ai = AlphaBeltaMaxAI()
        ranked = [(9, 9), (9, 10), (10, 9), (10, 10)]
        remembered = ((10, 9), (10, 10))

        ai._remember_pair(remembered, depth=3)
        pairs = ai._gen_pairs(ranked, 0, 2)

        self.assertEqual(pairs[0], remembered)

    def test_history_is_cleared_for_each_public_move_search(self):
        ai = AlphaBeltaMaxAI()
        ai._remember_pair(((10, 9), (10, 10)), depth=3)

        ai.get_moves(Board(19), BLACK, 1)

        self.assertEqual(ai._history_score, {})

    def test_killer_pair_is_ordered_first_for_matching_depth(self):
        ai = AlphaBeltaMaxAI()
        pairs = [
            ((9, 9), (9, 10)),
            ((10, 9), (10, 10)),
        ]

        ai._remember_killer(pairs[1], depth=2)
        ordered = ai._order_pairs_for_depth(pairs, depth=2)

        self.assertEqual(ordered[0], pairs[1])

    def test_killers_are_cleared_for_each_public_move_search(self):
        ai = AlphaBeltaMaxAI()
        ai._remember_killer(((10, 9), (10, 10)), depth=3)

        ai.get_moves(Board(19), BLACK, 1)

        self.assertEqual(ai._killer_pairs, {})

    def test_pvs_first_child_uses_full_window(self):
        ai = _ScriptedPVSMaxAI([-7])

        score = ai._pvs_child_score(
            opp_color=BLACK,
            child_depth=2,
            alpha=10,
            beta=20,
            deadline=999999.0,
            is_first_child=True,
        )

        self.assertEqual(score, 7)
        self.assertEqual(ai.calls, [(BLACK, 2, -20, -10)])

    def test_pvs_later_child_uses_null_window_when_it_fails_low(self):
        ai = _ScriptedPVSMaxAI([-10])

        score = ai._pvs_child_score(
            opp_color=BLACK,
            child_depth=2,
            alpha=10,
            beta=20,
            deadline=999999.0,
            is_first_child=False,
        )

        self.assertEqual(score, 10)
        self.assertEqual(ai.calls, [(BLACK, 2, -11, -10)])

    def test_pvs_later_child_researches_full_window_on_fail_high(self):
        ai = _ScriptedPVSMaxAI([-15, -17])

        score = ai._pvs_child_score(
            opp_color=BLACK,
            child_depth=2,
            alpha=10,
            beta=20,
            deadline=999999.0,
            is_first_child=False,
        )

        self.assertEqual(score, 17)
        self.assertEqual(ai.calls, [(BLACK, 2, -11, -10), (BLACK, 2, -20, -10)])

    def test_transposition_table_keeps_scores_separate_by_side_to_move(self):
        board = Board(19)
        for col in (5, 6, 7):
            self.assertTrue(board.place(Move(9, col, BLACK)))
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        black_score = ai._negamax(BLACK, 0, -20_000_000, 20_000_000, 999999.0)
        white_score = ai._negamax(WHITE, 0, -20_000_000, 20_000_000, 999999.0)

        self.assertGreater(black_score, 0)
        self.assertLess(white_score, 0)

    def test_root_hint_pair_is_ordered_first(self):
        ai = AlphaBeltaMaxAI()
        pairs = [
            ((9, 9), (9, 10)),
            ((10, 9), (10, 10)),
        ]
        ai._root_hint_pair = pairs[1]

        ordered = ai._order_root_pairs(pairs, depth=2)

        self.assertEqual(ordered[0], pairs[1])

    def test_root_bounds_use_previous_score_as_aspiration_center(self):
        ai = AlphaBeltaMaxAI()
        ai._last_root_score = 12345

        alpha, beta, used_aspiration = ai._root_bounds()

        self.assertEqual((alpha, beta), (12345 - 250000, 12345 + 250000))
        self.assertTrue(used_aspiration)

    def test_root_bounds_use_full_window_without_previous_score(self):
        ai = AlphaBeltaMaxAI()

        alpha, beta, used_aspiration = ai._root_bounds()

        self.assertEqual((alpha, beta), (-20000000, 20000000))
        self.assertFalse(used_aspiration)

    def test_active_root_bounds_keep_full_window_by_default(self):
        ai = AlphaBeltaMaxAI()
        ai._last_root_score = 12345

        alpha, beta, used_aspiration = ai._active_root_bounds()

        self.assertEqual((alpha, beta), (-20000000, 20000000))
        self.assertFalse(used_aspiration)

    def test_root_aspiration_fallback_triggers_on_fail_low_or_high(self):
        ai = AlphaBeltaMaxAI()

        self.assertTrue(ai._needs_full_root_research(-10, -10, 10, True))
        self.assertTrue(ai._needs_full_root_research(10, -10, 10, True))
        self.assertFalse(ai._needs_full_root_research(0, -10, 10, True))
        self.assertFalse(ai._needs_full_root_research(10, -10, 10, False))

    def test_finds_pair_that_creates_unblockable_immediate_win_cells(self):
        board = self._cross_four_board()
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        pair = ai._find_multi_threat_attack(ai._candidates(), BLACK, 2)

        self.assertIsNotNone(pair)
        self.assertIn((9, 9), pair)
        self.assertGreaterEqual(
            ai._winning_cells_after_pair(pair, BLACK, 0, limit=3),
            3,
        )

    def test_get_moves_prefers_multi_threat_attack_before_tree_search(self):
        board = self._cross_four_board()

        moves = AlphaBeltaMaxAI().get_moves(board, BLACK, 2)

        self.assertIn((9, 9), {(move.row, move.col) for move in moves})

    def test_finds_blocks_against_opponent_multi_threat_attack(self):
        board = self._white_cross_four_board()
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        blocks = ai._find_multi_threat_blocks(ai._candidates(), BLACK, 2)

        self.assertIsNotNone(blocks)
        self.assertIn((9, 9), blocks)

    def test_get_moves_blocks_opponent_multi_threat_before_tree_search(self):
        board = self._white_cross_four_board()

        moves = AlphaBeltaMaxAI().get_moves(board, BLACK, 2)

        self.assertIn((9, 9), {(move.row, move.col) for move in moves})

    def test_multi_threat_block_uses_one_stone_for_detected_pair(self):
        board = self._white_cross_four_board()
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)
        threat_pair = ai._find_multi_threat_attack(ai._candidates(), WHITE, 2)

        blocks = ai._find_multi_threat_blocks(ai._candidates(), BLACK, 2)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(len(set(blocks).intersection(set(threat_pair))), 1)

    def test_get_moves_uses_one_stone_to_block_one_sided_four(self):
        board = Board(19)
        self.assertTrue(board.place(Move(9, 4, BLACK)))
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, WHITE)))

        moves = AlphaBeltaMaxAI().get_moves(board, BLACK, 2)
        cells = {(move.row, move.col) for move in moves}
        threat_cells = {(9, 9), (9, 10)}

        self.assertEqual(len(cells), 2)
        self.assertEqual(len(cells.intersection(threat_cells)), 1)

    def test_records_decision_reason_for_tactical_block(self):
        board = Board(19)
        self.assertTrue(board.place(Move(9, 4, BLACK)))
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, WHITE)))
        ai = AlphaBeltaMaxAI()

        moves = ai.get_moves(board, BLACK, 2)

        self.assertEqual(ai.last_decision["reason"], "immediate_block")
        self.assertEqual(
            ai.last_decision["moves"],
            [(move.row, move.col) for move in moves],
        )

    def test_immediate_winning_cells_after_pair_returns_forced_replies(self):
        board = Board(19)
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, BLACK)))
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        cells = ai._immediate_winning_cells_after_pair(
            ((9, 9), (10, 10)),
            BLACK,
            0,
            limit=3,
        )

        self.assertEqual(set(cells), {(9, 4), (9, 10)})

    def test_forcing_threat_chain_returns_none_without_forced_replies(self):
        board = Board(19)
        for col in (5, 6, 7):
            self.assertTrue(board.place(Move(9, col, BLACK)))
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        pair = ai._find_forcing_threat_chain_attack(ai._candidates(), BLACK, 2)

        self.assertIsNone(pair)

    def test_finds_blocks_against_opponent_forcing_threat_chain(self):
        board = self._white_forcing_chain_board()
        ai = AlphaBeltaMaxAI()
        ai._init_from_board(board)

        blocks = ai._find_forcing_threat_chain_blocks(ai._candidates(), BLACK, 2)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(len(set(blocks).intersection({(12, 12), (11, 11)})), 1)

    def test_get_moves_blocks_opponent_forcing_threat_chain_before_search(self):
        board = self._white_forcing_chain_board()

        moves = AlphaBeltaMaxAI().get_moves(board, BLACK, 2)

        cells = {(move.row, move.col) for move in moves}

        self.assertEqual(len(cells), 2)
        self.assertEqual(len(cells.intersection({(12, 12), (11, 11)})), 1)

    def _max_extra_score(self, board: Board, row: int, col: int) -> int:
        plus = AlphaBeltaPlusAI()
        max_ai = AlphaBeltaMaxAI()
        plus._init_from_board(board)
        max_ai._init_from_board(board)
        return max_ai._cell_val(row, col, 0) - plus._cell_val(row, col, 0)

    def _cross_four_board(self) -> Board:
        board = Board(19)
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, BLACK)))
        for row in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(row, 9, BLACK)))
        return board

    def _white_cross_four_board(self) -> Board:
        board = Board(19)
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, WHITE)))
        for row in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(row, 9, WHITE)))
        return board

    def _white_forcing_chain_board(self) -> Board:
        board = Board(19)
        for col in (8, 9, 10):
            self.assertTrue(board.place(Move(12, col, WHITE)))
        for row in (8, 9, 10):
            self.assertTrue(board.place(Move(row, 12, WHITE)))
        for offset in (8, 9, 10):
            self.assertTrue(board.place(Move(offset, offset, WHITE)))
        return board


class _ScriptedPVSMaxAI(AlphaBeltaMaxAI):
    def __init__(self, scores):
        super().__init__()
        self._scores = list(scores)
        self.calls = []

    def _negamax(self, color, depth, alpha, beta, deadline):
        self.calls.append((color, depth, alpha, beta))
        return self._scores.pop(0)


if __name__ == "__main__":
    unittest.main()
