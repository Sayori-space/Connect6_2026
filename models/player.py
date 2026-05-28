from enum import Enum, auto
from utils.constants import BLACK


class PlayerType(Enum):
    HUMAN = auto()
    AI = auto()


class Player:
    def __init__(self, color: int, player_type: PlayerType, name: str = ""):
        self.color = color
        self.player_type = player_type
        self.name = name or ("黑方" if color == BLACK else "白方")

    def __repr__(self) -> str:
        return f"Player({self.name}, {self.player_type.name})"
