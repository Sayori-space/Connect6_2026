from dataclasses import dataclass, field
from models.player import PlayerType
from utils.constants import DEFAULT_BOARD_SIZE


@dataclass
class GameConfig:
    board_size: int = DEFAULT_BOARD_SIZE
    black_type: PlayerType = PlayerType.HUMAN
    white_type: PlayerType = PlayerType.HUMAN
    black_name: str = "黑方"
    white_name: str = "白方"
    ai_type: str = "alpha_beta"  # "alpha_beta"、"alpha_belta_plus" 或 "alpha_belta_max"
    ai_think_time_seconds: float = 15 * 60
