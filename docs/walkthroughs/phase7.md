# Phase 7 walkthrough — Tic-tac-toe + activities framework

Step-by-step manual validation for Phase 7. Everything here runs in **sim mode**
(`UARM_MODE=sim`, the default) — no hardware required.

## Prerequisites

- Phases 1-6 committed.
- `uv run pytest -q` shows **134 tests passing**.
- `uv run ruff check .` is clean.

## 1. Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

**Expected:** `134 passed`, `All checks passed!`.

## 2. CLI — list activities (no server)

```bash
uv run uarm activity list
```

**Expected (order may differ):**

```
draw-shapes    [runnable   ] Draw Shapes — Draw a square, triangle, star, or circle at a position.
tic-tac-toe    [interactive] Tic-Tac-Toe — Play tic-tac-toe against the arm — you are X, the arm is O.
```

## 3. CLI — play tic-tac-toe in the terminal (no server)

```bash
uv run uarm activity run tic-tac-toe
```

The arm "draws" the grid (slewing in sim), then prompts:

```
Your turn (X).
   |   |
---+---+---
   |   |
---+---+---
   |   |
Your move 'row col' (0-2), or 'q' to quit:
```

**Test:**
1. Enter `1 1` (center). After "Thinking…" the board shows your `X` and the
   arm's `O`.
2. Keep playing. Because the arm uses unbeatable minimax, you can only **lose
   or draw** — never win.
3. The game ends with `Game over: Arm wins.` or `Game over: Draw.`.
4. Enter `q` at any prompt to quit early.

**What you should NOT see:** you cannot beat the arm. If you ever see
`You win!`, that is a bug — report it.

## 4. CLI — draw a shape (no server)

```bash
uv run uarm activity run draw-shapes -o shape=star -o size=40
```

**Expected:** `draw-shapes complete.` after the arm slews through the star path.
Try `-o shape=square`, `triangle`, `circle`, and `-o center_x=240 -o center_y=20`.

An out-of-reach request is refused cleanly (no partial draw):

```bash
uv run uarm activity run draw-shapes -o shape=circle -o size=200
```

**Expected:** an error mentioning the point is outside the workspace; exit code 1.

## 5. Web UI — tic-tac-toe

Start the server:

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

**What you should see:**
- An **Activities** section at the top of the Controls panel with a dropdown.
- With **Tic-Tac-Toe** selected: grid-position inputs (cX / cY / cell), a
  **New Game** button, a 3×3 board, and a status line.

**Test:**
1. Click **New Game**. Status shows "Drawing grid…", the 3D arm draws the `#`,
   then status becomes "Your turn (X)."
2. Click an empty cell → it shows `X`, status shows "Thinking…", the arm draws
   an `O`, and the board updates. Watch the 3D arm move for every stroke.
3. Play to the end: status shows "Arm wins.", "Draw.", or "You win! 🎉" (you
   won't — the arm is unbeatable). On an arm win the wrist does a small wave; if
   you somehow drew, no celebration.
4. Change `cell` to e.g. `50` and click **New Game** — the drawn grid is larger.

**Drawing trace.** A white ink trace follows the tool tip whenever the pen is at
contact height, so you can see what the arm actually drew (the `#` grid, the
`X`s and `O`s) building up on the table plane in 3D. Orbit to a top-down view to
read it like paper. **New Game** clears the trace; the **Trace drawing** checkbox
and **Clear** button (top of the Activities panel) toggle and reset it. The trace
shows the *real* tip path, so near-straight strokes may bow slightly — that's the
arm's actual motion between waypoints, not a rendering artifact.

## 6. Web UI — draw shapes

1. In the Activities dropdown, choose **Draw Shapes**.
2. Pick a shape, set size/center, click **Draw**. The 3D arm draws it, and the
   white trace shows the resulting shape on the table plane. Draw several to
   compare; **Clear** wipes the trace.

## 7. CLI driving the running server (shared viz)

With the server still running, in another terminal:

```bash
uv run uarm activity run tic-tac-toe
```

**Expected:** the terminal game now drives the **same** arm as the web page —
open the browser alongside and watch the 3D arm draw as you type moves. (When no
server is running, the CLI falls back to a local arm with no viz.)

## What you should NOT see yet

- **No real pen drawing on hardware.** This phase is sim-validated only. On real
  hardware the pen contact height needs Z calibration (the commanded tool-tip Z
  is treated as the pen tip; the physical pen offset is absorbed into
  calibration). Do not run on hardware without Maz's go-ahead.
- **No wrist-down pen orientation.** The arm has no wrist pitch; drawing uses
  tool-tip Cartesian targets, not a downward-pointing pen in the model.
- **No concurrent games.** The server holds one interactive session at a time;
  starting a new game replaces the previous one.
- **No persistence.** Game state is in-memory; restarting the server clears it.
- **No difficulty setting.** The arm always plays optimally.
