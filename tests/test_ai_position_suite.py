import os
import unittest

from ai.evaluation import (
    evaluate_position,
    load_position_fixture,
    load_position_fixtures,
)
from ai.factory import build_ai
from models.game_config import GameConfig
from scripts.benchmark_ai import run_position_suite


FIXTURE_DIR = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "ai_positions",
)


class AIPositionSuiteTests(unittest.TestCase):
    def test_loads_position_fixture_and_rebuilds_board(self):
        position = load_position_fixture(
            os.path.join(FIXTURE_DIR, "black_two_stone_win.json")
        )

        board = position.build_board()

        self.assertEqual(position.position_id, "black_two_stone_win")
        self.assertEqual(board.size, 19)
        self.assertEqual(len(board.history), 4)
        self.assertEqual(position.color, 1)
        self.assertEqual(position.count, 2)
        self.assertEqual(position.recommended_cells, {(10, 4), (10, 5)})

    def test_loads_all_position_fixtures(self):
        positions = load_position_fixtures(FIXTURE_DIR)

        self.assertGreaterEqual(len(positions), 2)
        self.assertEqual(
            sorted(position.position_id for position in positions),
            sorted({position.position_id for position in positions}),
        )

    def test_position_suite_has_minimum_tactical_coverage(self):
        positions = load_position_fixtures(FIXTURE_DIR)

        self.assertGreaterEqual(len(positions), 20)

    def test_evaluates_alpha_belta_max_against_recommended_cells(self):
        position = load_position_fixture(
            os.path.join(FIXTURE_DIR, "black_two_stone_win.json")
        )
        ai = build_ai(GameConfig(ai_type="alpha_belta_max"))

        result = evaluate_position(position, ai)

        self.assertTrue(result.passed)
        self.assertEqual(result.selected_cells, {(10, 4), (10, 5)})
        self.assertLessEqual(result.elapsed_seconds, position.max_seconds)

    def test_evaluates_grouped_recommended_cells(self):
        position = load_position_fixture(
            os.path.join(FIXTURE_DIR, "black_blocks_one_sided_four.json")
        )
        ai = build_ai(GameConfig(ai_type="alpha_belta_max"))

        self.assertEqual(
            position.recommended_groups,
            (frozenset({(9, 9), (9, 10)}),),
        )

        result = evaluate_position(position, ai)

        self.assertTrue(result.passed, result.reason)
        self.assertTrue(result.selected_cells.intersection({(9, 9), (9, 10)}))

    def test_benchmark_runs_position_suite_for_engine(self):
        report = run_position_suite(FIXTURE_DIR, "alpha_belta_max")

        self.assertEqual(report.engine, "alpha_belta_max")
        self.assertGreaterEqual(report.total, 2)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.passed, report.total)
        self.assertEqual(report.pass_rate, 1.0)

        payload = report.to_dict()
        self.assertEqual(payload["pass_rate"], 1.0)
        self.assertIn("decision_reason", payload["results"][0])
        self.assertIn("search_nodes", payload["results"][0])
        self.assertIn("completed_depth", payload["results"][0])

    def test_benchmark_report_exports_csv(self):
        report = run_position_suite(FIXTURE_DIR, "alpha_belta_max")

        csv_text = report.to_csv()

        self.assertIn(
            "engine,position_id,passed,elapsed_seconds,reason,selected_cells",
            csv_text.splitlines()[0],
        )
        self.assertIn("alpha_belta_max,black_two_stone_win,true", csv_text)


if __name__ == "__main__":
    unittest.main()
