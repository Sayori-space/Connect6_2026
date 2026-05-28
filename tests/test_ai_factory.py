import unittest

from ai.alpha_beta_ai import AlphaBetaAI
from ai.factory import build_ai
from models.game_config import GameConfig


class AIFactoryTests(unittest.TestCase):
    def test_builds_alpha_belta_plus(self):
        ai = build_ai(GameConfig(ai_type="alpha_belta_plus"))

        self.assertEqual(ai.name, "alpha-belta-plus")

    def test_keeps_existing_alpha_beta(self):
        ai = build_ai(GameConfig(ai_type="alpha_beta"))

        self.assertIsInstance(ai, AlphaBetaAI)

    def test_applies_configured_think_time_to_pruning_ai(self):
        ai = build_ai(GameConfig(ai_type="alpha_belta_plus", ai_think_time_seconds=0.2))

        self.assertEqual(ai.think_time_seconds, 0.2)

    def test_builds_alpha_belta_max(self):
        ai = build_ai(GameConfig(ai_type="alpha_belta_max", ai_think_time_seconds=0.3))

        self.assertEqual(ai.name, "alpha-belta-max")
        self.assertEqual(ai.think_time_seconds, 0.3)


if __name__ == "__main__":
    unittest.main()
