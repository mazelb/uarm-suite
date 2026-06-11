# Phase 8C walkthrough — Draw-text activity

Step-by-step manual validation for 8C, the third proof of the activities
framework. Everything runs in **sim mode**.

## What 8C delivers

- `activities/draw_text.py` — a runnable `draw-text` activity with a built-in
  **single-stroke vector font**: A–Z, 0–9, space and `. , - + ! ? : '`. Every
  glyph is a few polylines on a 4×6-unit cell (no fills — pen-plotter style),
  so it draws through the same `draw_strokes` path as everything else and
  inherits straight lines, feed pacing, and whole-path validation.
- Page orientation matches the tic-tac-toe board: "up" on the page is +X,
  text advances toward −Y, so it reads left-to-right for the operator.
- Options: `text`, `size` (capital height, mm), `spacing`, `center_x`,
  `center_y`, plus the usual `table_z` / `pen_up` / `wrist` / `feed` /
  `travel_feed` (defaults from `drawing.json`).
- A **text widget** in the web UI next to the shapes widget.
- Bad input is a clean refusal: unsupported characters raise `ValueError`,
  surfaced as a CLI error / 422 toast — `/api/activities/{slug}/run` now
  catches `ValueError` like the interactive `start` already did.

## 1. Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

**Expected:** `181 passed`, `All checks passed!`.

## 2. It lists and runs from the CLI

```bash
uv run uarm activity list
uv run uarm activity run draw-text -o text=HI -o size=30
```

**Expected:** `draw-text` appears in the list; the run homes the arm, writes
"HI" centered at (250, 0), and prints `draw-text complete.`

Bad text refuses cleanly (exit code 1, no motion):

```bash
uv run uarm activity run draw-text -o text=héllo
```

**Expected:** `Error: unsupported character(s) 'é'; supported: …`

## 3. Watch it write in the 3D viz

Terminal 1: `uv run uvicorn server:app --port 8000`, open
<http://localhost:8000>. In **Activities**, pick **Draw Text** — the text
widget appears (message, Size, cX, cY). Write `HI!` at size 30.

**Expected:** the trace spells out the message, readable in the top-down view
(text runs across the table, baseline toward the base). Letters are straight
multi-stroke polylines; the pen lifts between strokes. Try `UARM 4EVER!` at
size 20 to see a longer string lay out and stay centered.

Unsupported characters (e.g. `café`) → error toast, no motion.

## 4. Feeds apply here too

```bash
uv run uarm activity run draw-text -o text=OK -o feed=15
```

**Expected:** visibly slow, constant-speed pen-down strokes — same feed
machinery as 8B, no special-casing.

## What you should NOT see yet (deferred)

- **No lowercase glyphs, accents, or multi-line text.** Input is uppercased;
  one line only. Wrap/diacritics are not planned — keep messages short.
- **No proportional spacing.** The font is monospace (4-unit cells + fixed
  gap); an `I` takes the same advance as a `W`.
- **No auto-shrink to fit the workspace.** Too-long text at too-big a size
  refuses with a workspace error rather than resizing itself — same
  no-silent-clamp rule as everywhere else.
