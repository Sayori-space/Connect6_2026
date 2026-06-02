# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the application

```bash
py -3 main.py
```

Python 3.12 is at `C:\Users\Sonk\AppData\Local\Programs\Python\Python312\`. There are no tests and no build step. Dependencies: `PyQt5`, `PyOpenGL` (optional — falls back to static star background if absent).

## Game rules

Connect6 (六子棋): Black places **1 stone** on the very first move; every subsequent turn both players place **2 stones**. First to form **6 in a row** (horizontal, vertical, or diagonal) wins.

## Architecture

### Layer separation

```
models/          Pure data: Move (frozen dataclass), Player, GameConfig
game/            Pure logic: Board (grid + history), rules (check_win, stones_per_turn), GameManager
ai/              AI engines: BaseAI (ABC), AlphaBetaAI, RandomAI
ui/              All PyQt5 code — no game logic here
utils/constants  Shared constants (EMPTY/BLACK/WHITE, animation params)
```

`game/` and `ai/` have **zero PyQt5 dependency**. Never import UI code from there.

### Navigation flow

`AppWindow` owns a `QStackedWidget` with four fixed pages:

| Index | Constant | Widget |
|-------|----------|--------|
| 0 | `_PAGE_HOME` | `HomeScreen` |
| 1 | `_PAGE_GAME` | `GamePage` |
| 2 | `_PAGE_RULES` | `RulesScreen` |
| 3 | `_PAGE_AI_CFG` | `AIConfigPage` |

Pages never navigate themselves — they emit signals (`go_back`, `game_config_ready`, etc.) and `AppWindow` switches pages.

### GameManager callback API

`GamePage` wires its UI to `GameManager` exclusively through callbacks (not inheritance or polling):

```python
manager.on_stone_placed    = fn(Move)
manager.on_turn_changed    = fn(color: int, stones_needed: int)
manager.on_game_over       = fn(winner: Optional[int], line: List[Tuple])
manager.on_undo            = fn(undone: List[Move])
manager.on_request_ai_move = fn(color: int)
manager.on_confirm_needed  = fn()
manager.on_stone_removed   = fn(Move)
```

Human turns require `confirm_turn()` before `_advance_turn` fires. AI turns advance automatically after `try_place` completes all required stones.

### Turn counting

`GameManager._turn_history` records the stone-count of each **completed** GameManager turn (e.g. `[1, 2, 2, 2, ...]`). `pending_moves` holds stones placed in the **current** in-progress turn. The chess record format (`chess_manual/*.txt`) groups consecutive black+white gm-turns into rounds.

### AI interface

Subclass `BaseAI` and implement:

```python
def get_moves(self, board: Board, color: int, count: int) -> List[Move]: ...
@property
def name(self) -> str: ...
```

`board` is a snapshot copy — safe to read, must not be mutated. `count` is 1 on the first move of the game, 2 otherwise. Register the AI in `GamePage.start_game()`.

### AlphaBetaAI internals

Key internal state (all flat arrays over the 19×19 grid):
- `_fg` — flat grid values
- `_cc` — candidate counter (number of neighbouring stones within radius 2)
- `_wcnt[w][color]` — per-window stone counts, updated O(24) per placement
- `_escore[color]` — incremental positional score, O(1) query via `_eval()`
- `_hash` — Zobrist hash for transposition table

`_place`/`_remove` keep all four structures in sync. `get_moves` rebuilds state from `board.history` at the start of each call.

### UI components

**`PixelButton`** (`ui/pixel_widgets.py`) — retro double-border button. Normal: transparent bg + white border/text. Hover: white fill + black border/text (animated via `_hover_progress` float driven by a 16 ms `QTimer`).

**`BoardWidget`** — handles all board rendering and mouse input. `set_current_turn_stones(cells)` highlights the in-progress turn's stones with a contrasting centre dot.

**`StarBackground` / `ShaderBackground`** — `pixel_widgets.py` tries to import `ShaderBackground` (OpenGL animated nebula) and replaces the static `StarBackground` alias if successful.

### Theme

All colours live in `ui/theme.py`. The palette is pure black/white with a single gold accent (`WIN_GLOW = "#FFE040"`). Do **not** use `letter-spacing` in stylesheets — it breaks CJK rendering on Windows. Set button fonts explicitly via `setFont()`, not stylesheet inheritance.

### Chess record format

Saved to `chess_manual/YYYY-MM-DDTHH-MM-SS.txt` as JSON:

```json
{"1": [{"B": "(r, c)"}, {"W": "(r, c)"}, ...], "2": [...]}
```

Each key is a round number (string); each value is a flat list of single-key dicts alternating black and white stones for that round.
