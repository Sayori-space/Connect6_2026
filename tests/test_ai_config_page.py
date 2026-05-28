import unittest

from models.player import PlayerType
from ui.ai_config_page import (
    AI_OPTIONS,
    _ai_type_from_label,
    _build_ai_game_config,
    _think_time_seconds_from_label,
)


class AIConfigPageTests(unittest.TestCase):
    def test_maps_ai_labels_to_config_values(self):
        self.assertEqual(_ai_type_from_label(AI_OPTIONS[0]), "alpha_beta")
        self.assertEqual(_ai_type_from_label("alpha-belta-plus"), "alpha_belta_plus")
        self.assertEqual(_ai_type_from_label("alpha-belta-max"), "alpha_belta_max")

    def test_public_ai_options_exclude_deep_learning_entrypoint(self):
        self.assertTrue(all("AlphaGo" not in label for label in AI_OPTIONS))

    def test_maps_think_time_labels_to_seconds(self):
        self.assertEqual(_think_time_seconds_from_label("0.5s"), 0.5)
        self.assertEqual(_think_time_seconds_from_label("1.0s"), 1.0)
        self.assertEqual(_think_time_seconds_from_label("2.5s"), 2.5)
        self.assertEqual(_think_time_seconds_from_label("5.0s"), 5.0)

    def test_builds_config_with_selected_ai_and_think_time_for_black_player(self):
        config = _build_ai_game_config(
            selected_color=1,
            ai_label="alpha-belta-max",
            think_time_label="5.0s",
        )

        self.assertEqual(config.black_type, PlayerType.HUMAN)
        self.assertEqual(config.white_type, PlayerType.AI)
        self.assertEqual(config.ai_type, "alpha_belta_max")
        self.assertEqual(config.ai_think_time_seconds, 5.0)

    def test_builds_config_with_selected_ai_and_think_time_for_white_player(self):
        config = _build_ai_game_config(
            selected_color=2,
            ai_label="alpha-belta-plus",
            think_time_label="1.0s",
        )

        self.assertEqual(config.black_type, PlayerType.AI)
        self.assertEqual(config.white_type, PlayerType.HUMAN)
        self.assertEqual(config.ai_type, "alpha_belta_plus")
        self.assertEqual(config.ai_think_time_seconds, 1.0)


if __name__ == "__main__":
    unittest.main()
