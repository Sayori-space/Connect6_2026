import unittest

from scripts.self_play_ai import (
    run_paired_self_play_series,
    run_self_play_match,
    run_self_play_series,
)
from utils.constants import BLACK, WHITE


class AISelfPlayTests(unittest.TestCase):
    def test_runs_bounded_self_play_match(self):
        result = run_self_play_match(
            black_engine="alpha_beta",
            white_engine="alpha_beta",
            max_turns=2,
            move_time_seconds=0.001,
        )

        self.assertEqual(result.black_engine, "alpha_beta")
        self.assertEqual(result.white_engine, "alpha_beta")
        self.assertGreater(result.stones_played, 0)
        self.assertLessEqual(result.turns_completed, 2)
        self.assertIn(result.winner, {BLACK, WHITE, None})
        self.assertIsNone(result.timeout_color)

    def test_runs_self_play_series_summary(self):
        summary = run_self_play_series(
            black_engine="alpha_beta",
            white_engine="alpha_beta",
            games=2,
            max_turns=1,
            move_time_seconds=0.001,
        )

        self.assertEqual(summary.games, 2)
        self.assertEqual(summary.black_engine, "alpha_beta")
        self.assertEqual(summary.white_engine, "alpha_beta")
        self.assertEqual(
            summary.black_wins + summary.white_wins + summary.draws,
            2,
        )

    def test_self_play_total_time_mode_declares_draw_on_timeout(self):
        result = run_self_play_match(
            black_engine="alpha_beta",
            white_engine="alpha_beta",
            max_turns=2,
            total_time_seconds=0,
        )

        self.assertIsNone(result.winner)
        self.assertEqual(result.timeout_color, BLACK)
        self.assertEqual(result.stones_played, 0)

    def test_self_play_series_exports_csv(self):
        summary = run_self_play_series(
            black_engine="alpha_beta",
            white_engine="alpha_beta",
            games=1,
            max_turns=1,
            move_time_seconds=0.001,
        )

        csv_text = summary.to_csv()

        self.assertIn(
            "game,black_engine,white_engine,winner,timeout_color,turns_completed,stones_played,elapsed_seconds",
            csv_text.splitlines()[0],
        )
        self.assertIn("alpha_beta,alpha_beta", csv_text)

    def test_self_play_series_csv_includes_remaining_time(self):
        summary = run_self_play_series(
            black_engine="alpha_beta",
            white_engine="alpha_beta",
            games=1,
            max_turns=1,
            total_time_seconds=1.0,
        )

        csv_lines = summary.to_csv().splitlines()

        self.assertIn(
            "black_remaining_seconds,white_remaining_seconds",
            csv_lines[0],
        )
        self.assertEqual(len(csv_lines[1].split(",")), len(csv_lines[0].split(",")))

    def test_runs_paired_self_play_series_with_swapped_colors(self):
        summary = run_paired_self_play_series(
            engine_a="alpha_beta",
            engine_b="alpha_belta_plus",
            pairs=1,
            max_turns=1,
            move_time_seconds=0.001,
        )

        self.assertEqual(summary.engine_a, "alpha_beta")
        self.assertEqual(summary.engine_b, "alpha_belta_plus")
        self.assertEqual(summary.games, 2)
        self.assertEqual(len(summary.results), 2)
        self.assertEqual(summary.results[0].black_engine, "alpha_beta")
        self.assertEqual(summary.results[0].white_engine, "alpha_belta_plus")
        self.assertEqual(summary.results[1].black_engine, "alpha_belta_plus")
        self.assertEqual(summary.results[1].white_engine, "alpha_beta")
        self.assertEqual(
            summary.engine_a_wins + summary.engine_b_wins + summary.draws,
            2,
        )


if __name__ == "__main__":
    unittest.main()
