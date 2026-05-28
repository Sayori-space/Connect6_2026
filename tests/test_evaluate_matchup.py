import subprocess
import sys
import unittest
from pathlib import Path

from ai.evaluate_matchup import OPENING_SUITE, run_head_to_head, run_matchup
from utils.constants import BLACK, WHITE


class EvaluateMatchupTests(unittest.TestCase):
    def test_run_matchup_swaps_colors_and_returns_summary(self):
        result = run_matchup(max_games=2, max_turns=4, think_time=0.01)

        self.assertEqual(result["games"], 2)
        self.assertIn("plus_wins", result)
        self.assertIn("baseline_wins", result)
        self.assertIn("draws", result)
        self.assertEqual(len(result["game_results"]), 2)
        self.assertEqual(
            {game["plus_color"] for game in result["game_results"]},
            {BLACK, WHITE},
        )

    def test_run_matchup_can_record_move_diagnostics(self):
        result = run_matchup(
            max_games=1,
            max_turns=3,
            think_time=0.05,
            record_moves=True,
        )

        game = result["game_results"][0]
        self.assertIn("move_log", game)
        self.assertGreaterEqual(len(game["move_log"]), 1)
        first = game["move_log"][0]
        self.assertIn("ai_name", first)
        self.assertIn("color", first)
        self.assertIn("moves", first)
        self.assertIn("elapsed_ms", first)
        self.assertIn("stats", first)
        self.assertIn("decision", first)
        self.assertIn("nodes", first["stats"])
        self.assertIn("tactical_pairs", first["stats"])
        self.assertIn("completed_depth", first["stats"])
        searched_plus_turns = [
            entry
            for entry in game["move_log"]
            if entry["ai_name"] == "alpha-belta-plus" and len(entry["moves"]) == 2
        ]
        self.assertTrue(searched_plus_turns)
        self.assertGreater(searched_plus_turns[0]["stats"]["tactical_pairs"], 0)
        self.assertGreater(searched_plus_turns[0]["stats"]["nodes"], 0)

    def test_script_runs_when_invoked_by_file_path(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "ai/evaluate_matchup.py",
                "--max-games",
                "1",
                "--max-turns",
                "2",
                "--think-time",
                "0.01",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("games=1", result.stdout)

    def test_script_prints_recorded_decision_when_recording_moves(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "ai/evaluate_matchup.py",
                "--challenger",
                "alpha_belta_max",
                "--max-games",
                "1",
                "--max-turns",
                "2",
                "--think-time",
                "0.01",
                "--record-moves",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision=", result.stdout)

    def test_run_matchup_can_use_alpha_belta_max_challenger(self):
        result = run_matchup(
            challenger="alpha_belta_max",
            max_games=1,
            max_turns=2,
            think_time=0.01,
        )

        self.assertEqual(result["challenger"], "alpha_belta_max")
        self.assertEqual(result["games"], 1)
        self.assertEqual(result["game_results"][0]["challenger_color"], BLACK)

    def test_alpha_belta_max_records_root_search_diagnostics(self):
        result = run_matchup(
            challenger="alpha_belta_max",
            max_games=1,
            max_turns=4,
            think_time=0.05,
            record_moves=True,
        )

        max_turns = [
            entry
            for entry in result["game_results"][0]["move_log"]
            if entry["ai_name"] == "alpha-belta-max" and len(entry["moves"]) == 2
        ]

        self.assertTrue(max_turns)
        self.assertGreater(max_turns[0]["stats"]["root_calls"], 0)
        self.assertGreater(max_turns[0]["stats"]["completed_depth"], 0)
        self.assertIn("reason", max_turns[0]["decision"])

    def test_run_head_to_head_compares_named_ais_and_swaps_colors(self):
        result = run_head_to_head(
            ai_a="alpha_belta_max",
            ai_b="alpha_belta_plus",
            think_times=[0.01],
            max_games=2,
            max_turns=2,
        )

        self.assertEqual(result["ai_a"], "alpha_belta_max")
        self.assertEqual(result["ai_b"], "alpha_belta_plus")
        self.assertEqual(result["games"], 2)
        self.assertIn("ai_a_wins", result)
        self.assertIn("ai_b_wins", result)
        self.assertIn("draws", result)
        self.assertEqual(
            {game["ai_a_color"] for game in result["game_results"]},
            {BLACK, WHITE},
        )
        self.assertEqual({game["think_time"] for game in result["game_results"]}, {0.01})

    def test_opening_suite_has_named_positions(self):
        self.assertGreaterEqual(len(OPENING_SUITE), 5)
        self.assertTrue(all(opening.name for opening in OPENING_SUITE))

    def test_run_head_to_head_can_use_opening_suite_and_summarize_decisions(self):
        result = run_head_to_head(
            ai_a="alpha_belta_max",
            ai_b="alpha_belta_plus",
            think_times=[0.01],
            max_games=2,
            max_turns=4,
            record_moves=True,
            opening_suite=True,
        )

        self.assertEqual(result["games"], 2)
        self.assertIn("decision_summary", result)
        self.assertIn("alpha-belta-max", result["decision_summary"])
        self.assertTrue(result["game_results"][0]["opening_name"])
        self.assertGreater(
            sum(result["decision_summary"]["alpha-belta-max"].values()),
            0,
        )


if __name__ == "__main__":
    unittest.main()
