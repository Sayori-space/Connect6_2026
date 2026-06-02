import unittest
import os
import time
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from game.game_manager import GameState
from models.move import Move
from ui.main_window import GamePage
from ui.control_panel import ControlPanel
from ui.control_panel import _format_turn_seconds
from utils.constants import BLACK


class _BlockingAI:
    def __init__(self):
        self.release = Event()

    @property
    def name(self):
        return "blocking"

    def get_moves(self, board, color, count):
        self.release.wait(0.5)
        return [Move(0, 0, color)]


class _RecordingAI:
    def __init__(self):
        self.think_time_seconds = None

    @property
    def name(self):
        return "recording"

    def get_moves(self, board, color, count):
        return [Move(0, 0, color)]


class _BoardSnapshot:
    def __init__(self, empty_count=8):
        self._empty_count = empty_count

    def copy(self):
        return self

    def get_all_empty(self):
        return [(0, col) for col in range(self._empty_count)]


class _ManagerStub:
    state = GameState.WAITING
    stones_needed_this_turn = 1
    board = _BoardSnapshot()
    current_color = BLACK

    def __init__(self):
        self.placed = []
        self.draw_declared = False

    def try_place(self, row, col):
        self.placed.append((row, col))
        return True

    def declare_draw(self):
        self.draw_declared = True
        self.state = GameState.GAME_OVER
        return True


class TurnTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_formats_turn_seconds_as_minutes_and_seconds(self):
        self.assertEqual(_format_turn_seconds(0), "00:00")
        self.assertEqual(_format_turn_seconds(9), "00:09")
        self.assertEqual(_format_turn_seconds(65), "01:05")
        self.assertEqual(_format_turn_seconds(900), "15:00")
        self.assertEqual(_format_turn_seconds(3601), "60:01")

    def test_panel_displays_ai_remaining_time(self):
        panel = ControlPanel()

        panel.update_ai_time_remaining(900)

        self.assertIn("15:00", panel._timer_lbl.text())

    def test_ai_move_execution_does_not_block_turn_timer(self):
        page = GamePage()
        ai = _BlockingAI()
        manager = _ManagerStub()
        page._manager = manager
        page._ai = {BLACK: ai}
        page._pending_ai_color = BLACK

        started = time.monotonic()
        page._execute_ai_move()
        elapsed = time.monotonic() - started

        ai.release.set()
        page.deleteLater()

        self.assertLess(elapsed, 0.2)

    def test_ai_receives_time_slice_instead_of_full_game_budget(self):
        page = GamePage()
        ai = _RecordingAI()
        manager = _ManagerStub()
        page._manager = manager
        page._ai = {BLACK: ai}
        page._ai_time_remaining = {BLACK: 7.5}
        page._pending_ai_color = BLACK

        page._execute_ai_move()
        page.deleteLater()

        self.assertEqual(ai.think_time_seconds, 5.0)
        self.assertLess(ai.think_time_seconds, 7.5)

    def test_ai_time_expiry_declares_draw_without_starting_search(self):
        page = GamePage()
        ai = _RecordingAI()
        manager = _ManagerStub()
        page._manager = manager
        page._ai = {BLACK: ai}
        page._ai_time_remaining = {BLACK: 0}
        page._pending_ai_color = BLACK

        page._execute_ai_move()
        page.deleteLater()

        self.assertTrue(manager.draw_declared)
        self.assertIsNone(ai.think_time_seconds)

    def test_threaded_ai_result_places_stone_when_ready(self):
        page = GamePage()
        ai = _BlockingAI()
        manager = _ManagerStub()
        page._manager = manager
        page._ai = {BLACK: ai}
        page._pending_ai_color = BLACK

        page._execute_ai_move()
        ai.release.set()

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not manager.placed:
            self._app.processEvents()
            time.sleep(0.01)

        page.deleteLater()

        self.assertEqual(manager.placed, [(0, 0)])


if __name__ == "__main__":
    unittest.main()
