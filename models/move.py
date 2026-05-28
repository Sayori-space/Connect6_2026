from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    """Immutable record of a single stone placement."""
    row: int
    col: int
    color: int  # BLACK or WHITE (see utils.constants)
