import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.move import Move
from utils.chess_manual import build_chess_manual_filename, build_chess_manual_record
from utils.constants import BLACK, WHITE


TEMP_ROOT = Path("D:/tmp")


class ChessManualFilenameTests(unittest.TestCase):
    def test_builds_competition_filename_for_first_player_win(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            filename = build_chess_manual_filename(
                Path(tmp),
                "参赛队A",
                "参赛队B",
                BLACK,
            )

        self.assertEqual(filename, "C6-参赛队A vs参赛队B-先手胜 (1).txt")

    def test_increments_suffix_when_filename_exists(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            manual_dir = Path(tmp)
            existing = manual_dir / "C6-参赛队A vs参赛队B-后手胜 (1).txt"
            existing.write_text("old", encoding="utf-8")

            filename = build_chess_manual_filename(
                manual_dir,
                "参赛队A",
                "参赛队B",
                WHITE,
            )

        self.assertEqual(filename, "C6-参赛队A vs参赛队B-后手胜 (2).txt")

    def test_builds_competition_record_body(self):
        moves = [
            Move(9, 9, BLACK),
            Move(10, 8, WHITE),
            Move(11, 8, WHITE),
            Move(10, 10, BLACK),
        ]

        record = build_chess_manual_record(
            moves,
            BLACK,
            datetime(2017, 12, 12, 14, 26),
        )

        self.assertEqual(
            record,
            "{[C6][][][先手胜][2017-12-12 14:26 ][]"
            ";B(J,10);W(I,11);W(I,12);B(K,11)}",
        )


if __name__ == "__main__":
    unittest.main()
