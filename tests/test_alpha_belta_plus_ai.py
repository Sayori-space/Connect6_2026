import unittest

from ai.alpha_belta_plus_ai import AlphaBeltaPlusAI
from game.board import Board
from models.move import Move
from utils.constants import BLACK, WHITE


class AlphaBeltaPlusAITests(unittest.TestCase):
    def test_blocks_double_immediate_win_threat(self):
        board = Board(19)
        for row, col, color in [
            (0, 0, WHITE),
            (1, 0, WHITE),
            (2, 0, WHITE),
            (3, 0, WHITE),
            (4, 0, WHITE),
            (0, 1, WHITE),
            (1, 1, WHITE),
            (2, 1, WHITE),
            (3, 1, WHITE),
            (4, 1, WHITE),
        ]:
            self.assertTrue(board.place(Move(row, col, color)))

        moves = AlphaBeltaPlusAI().get_moves(board, BLACK, 2)

        self.assertEqual({(m.row, m.col) for m in moves}, {(5, 0), (5, 1)})

    def test_finds_two_stone_immediate_win(self):
        board = Board(19)
        for col in range(4):
            self.assertTrue(board.place(Move(10, col, BLACK)))

        moves = AlphaBeltaPlusAI().get_moves(board, BLACK, 2)

        self.assertEqual({(m.row, m.col) for m in moves}, {(10, 4), (10, 5)})

    def test_exact_threat_blocks_cover_all_pair_threats(self):
        board = Board(19)
        for row in (0, 1):
            for col in range(4):
                self.assertTrue(board.place(Move(row, col, WHITE)))

        ai = AlphaBeltaPlusAI()
        ai._init_from_board(board)
        threats = ai._find_pair_threats(
            [(0, 4), (0, 5), (1, 4), (1, 5)],
            WHITE,
            1,
        )

        blocks = ai._choose_blocks_for_pair_threats(threats, 0, 2)

        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(set(blocks).intersection(pair) for pair in threats))

    def test_pair_threat_block_uses_single_cover_when_one_cell_is_enough(self):
        board = Board(19)
        self.assertTrue(board.place(Move(9, 4, BLACK)))
        for col in (5, 6, 7, 8):
            self.assertTrue(board.place(Move(9, col, WHITE)))

        ai = AlphaBeltaPlusAI()
        ai._init_from_board(board)
        threats = ai._find_pair_threats([(9, 9), (9, 10)], WHITE, 1)

        blocks = ai._choose_blocks_for_pair_threats(threats, 0, 2)

        self.assertEqual(len(blocks), 1)
        self.assertIn(blocks[0], {(9, 9), (9, 10)})

    def test_pair_ordering_prefers_future_winning_continuations(self):
        board = Board(19)
        for col in range(5):
            self.assertTrue(board.place(Move(7, col, BLACK)))
        for row in range(5):
            self.assertTrue(board.place(Move(row, 7, BLACK)))

        ai = AlphaBeltaPlusAI()
        ai._init_from_board(board)

        wins = ai._count_immediate_winning_cells(
            [(7, 5), (5, 7), (12, 12)],
            BLACK,
            0,
        )

        self.assertEqual(wins, 2)


if __name__ == "__main__":
    unittest.main()
