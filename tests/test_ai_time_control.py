import unittest

from ai.time_control import allocate_ai_move_time


class AITimeControlTests(unittest.TestCase):
    def test_allocates_fraction_of_remaining_budget_for_early_game(self):
        budget = allocate_ai_move_time(
            remaining_seconds=900,
            empty_count=360,
            stones_this_turn=2,
        )

        self.assertGreater(budget, 9)
        self.assertLess(budget, 11)
        self.assertLess(budget, 900)

    def test_urgency_increases_budget_without_exceeding_remaining_time(self):
        normal = allocate_ai_move_time(
            remaining_seconds=60,
            empty_count=40,
            stones_this_turn=2,
            urgency=1.0,
        )
        urgent = allocate_ai_move_time(
            remaining_seconds=60,
            empty_count=40,
            stones_this_turn=2,
            urgency=2.5,
        )

        self.assertGreater(urgent, normal)
        self.assertLessEqual(urgent, 60)

    def test_zero_remaining_time_allocates_zero(self):
        self.assertEqual(
            allocate_ai_move_time(
                remaining_seconds=0,
                empty_count=40,
                stones_this_turn=2,
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
