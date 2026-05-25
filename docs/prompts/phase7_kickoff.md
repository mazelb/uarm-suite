# Phase 7 kickoff prompt — Tic-tac-toe + extensible activities framework

## Where we are

Phases 1-6 are committed. The arm control suite is complete:
- Full IK/FK, sim bus, PCA9685 hardware bus
- CLI + FastAPI server + 3D web UI with controls
- Recording/replay, calibration wizard, workspace viz, soft-limit toasts
- 98 tests passing

## Project motivation

This project started as a fun father-and-kid build to make a uArm Swift
play tic-tac-toe. Phases 1-6 built the general-purpose arm control stack.
Phase 7 brings the original goal to life: an interactive tic-tac-toe game
where a human plays against the arm, plus a framework so more games and
activities can be added without touching the core arm code.

## What to build

### 7A: Activities framework (`activities/`)

A lightweight plugin system for arm-driven activities:

```
activities/
├── __init__.py          — ActivityBase protocol + registry
├── tic_tac_toe.py       — first activity
└── draw_shapes.py       — second activity (demo/stretch)
```

**ActivityBase protocol:**
```python
class ActivityBase(Protocol):
    name: str                     # display name ("Tic-Tac-Toe")
    description: str              # one-liner
    def setup(self, arm: UArm) -> None: ...
    def run(self, arm: UArm) -> None: ...
    def cleanup(self, arm: UArm) -> None: ...
```

**Registry:** auto-discovers activities in the `activities/` directory.
Server exposes `/api/activities` (list) and `/api/activities/{name}/run` (execute).
Web UI gets an "Activities" panel listing available activities with a Run button.

### 7B: Tic-tac-toe game

**Physical setup:**
- 3x3 grid drawn/printed on paper, positioned in the arm's workspace
- Grid center at approximately (250, 0, 0) — configurable
- Cell size ~40mm — configurable
- The arm holds a pen/marker (attached to tool tip)

**Game flow:**
1. User starts the activity from the web UI or CLI
2. Arm draws the grid (two horizontal + two vertical lines)
3. Human plays first (X). They tap a cell on the web UI grid widget
4. Arm responds: computes best move, draws O in the chosen cell
5. Repeat until win/draw
6. Arm celebrates (small wave) or hangs head (loss)

**Components:**

1. **Board model** (`activities/tic_tac_toe.py`):
   - 3x3 array, X/O/empty
   - Win/draw detection
   - Cell → world coordinates mapping (configurable grid origin, spacing)

2. **AI opponent** (minimax, unbeatable):
   - Pure function: `best_move(board, player) -> (row, col)`
   - Minimax with alpha-beta pruning
   - O always plays optimally

3. **Drawing routines**:
   - `draw_grid(arm)` — move along path to draw the # shape
   - `draw_x(arm, row, col)` — two diagonal strokes inside the cell
   - `draw_o(arm, row, col)` — approximate circle (8-segment polygon)
   - Pen-up/pen-down: raise Z +20mm between strokes

4. **Web UI widget** (in activities panel):
   - 3x3 clickable grid showing current board state
   - "New Game" button
   - Status text (your turn / thinking / X wins / draw)
   - Grid position config (center X/Y, cell size)

5. **Sim mode**: full game works in sim — the 3D viz shows the arm
   drawing. No physical pen needed.

6. **Hardware mode**: same flow, but arm actually draws with a pen.
   Requires Z calibration for pen contact height.

**API endpoints:**
```
GET  /api/activities                     — list activities
POST /api/activities/tic-tac-toe/start   — begin new game, arm draws grid
POST /api/activities/tic-tac-toe/move    — human plays {row, col}
GET  /api/activities/tic-tac-toe/state   — current board + whose turn
```

### 7C: CLI integration

```bash
uarm activity list                       # list available activities
uarm activity run tic-tac-toe            # start interactive game in terminal
```

Terminal game: prints the board, asks for row/col input, sends arm moves.

### 7D: Second activity — draw shapes (demo)

A simpler activity to prove the framework isn't tic-tac-toe-specific:
- Draw a square, triangle, star, or circle at a given position
- User picks shape and size from the web UI
- Arm draws it

## Lessons from Phase 6

1. **LatheGeometry works for workspace viz.** The 2D cross-section approach
   with client-side Three.js rendering avoids coordinate-mapping bugs.

2. **Calibration persists to calibration.json.** Activities that need
   physical accuracy (pen drawing) should document that calibration is
   a prerequisite.

3. **Soft-limit toasts use client-side limit checking.** Activities should
   pre-validate paths against workspace limits before sending moves,
   rather than relying on toast feedback.

4. **SERVO_CALIBRATION is a mutable global dict.** Any module that imports
   it from config gets a reference to the same dict. Activities don't need
   special calibration handling.

## Key constraints

- Activities must not import hardware libraries directly — they talk
  through UArm only
- Tic-tac-toe AI must be deterministic (minimax) so replays work
- Drawing paths should be tested with FK round-trip to verify all points
  are reachable before sending to the arm
- The web UI grid widget must work in both sim and hardware modes
- No external dependencies beyond what's already in pyproject.toml
  (numpy/scipy NOT needed — minimax and path generation are simple enough)
- Keep the "no build step" rule — vanilla JS for the grid widget

## Test plan

- Unit tests for minimax AI (known board states → expected moves)
- Unit tests for cell-to-coordinate mapping
- Unit tests for activity registry (discover, list, run)
- Integration test: full game sim (9 moves, detect outcome)
- Path validation: all drawing paths are within workspace
- Test draw routines produce correct move sequences

## Estimated scope

| Sub-phase | Scope | Effort |
|---|---|---|
| 7A | Activities framework + registry + API | Small |
| 7B | Tic-tac-toe: board, AI, drawing, web widget | Medium |
| 7C | CLI `uarm activity` commands | Small |
| 7D | Draw-shapes activity | Small |

Total: medium-sized phase. Can be split into 7A+7B first, 7C+7D second
if needed.
