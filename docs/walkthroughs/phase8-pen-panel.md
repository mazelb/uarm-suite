# Phase 8 walkthrough — Web-UI pen panel

Step-by-step manual validation for the pen panel (the last deferred 8A item).
Everything runs in **sim mode**; on the Pi this same panel is how you'll do
pen calibration without juggling a terminal next to the arm.

## What this delivers

`drawing.json` was CLI-only (`uarm pen show/set/calibrate/jog-corners`). Now:

- **Server endpoints**: `GET /api/pen` (config + effective feeds),
  `POST /api/pen` (partial update + save; an explicit `null` clears a feed
  override back to the suite default), `POST /api/pen/jog-corners` (the
  dry-run, straight-line edges at the travel feed).
- **Pen panel** in the web UI (between *Go To* and *Workspace*): table Z,
  lift, wrist, pen label, draw/travel feeds (empty = suite default, shown as
  the placeholder), **Use current Z**, Save, and a grid dry-run widget.
- Browser-based pen calibration = existing **Jog Z buttons** + **Use current
  Z** + **Save** — same flow as `uarm pen calibrate`, no terminal needed.
- The draw-shapes trace now mirrors the *persisted* pen geometry instead of
  hardcoded `(0, 20)`.

## 1. Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

**Expected:** `171 passed`, `All checks passed!`.

## 2. The panel round-trips the config

Terminal 1: `uv run uvicorn server:app --port 8000`, open <http://localhost:8000>.

In the **Pen** section: Table Z `0`, Lift `20`, Feed/Travel empty with
placeholders `40` / `120`. Set Table Z to `-25`, Feed to `60`, label
`Sharpie`, hit **Save** → "Pen config saved" toast. Then in terminal 2:

```bash
uv run uarm pen show
```

**Expected:** `table_z = -25.0`, `feed = 60.0 mm/s (pen down)` with *no*
"(suite default)" marker, `pen = Sharpie` — the CLI and panel share
`drawing.json`. The reverse works too (`uarm pen set --table-z -30`, reload
the page, the panel shows -30).

Clear the Feed field and Save again → `uarm pen show` is back to
`feed = 40.0 … (suite default — tune on paper)`.

## 3. Browser pen calibration (the Pi workflow, rehearsed)

1. **Go To** `250, 0, 50`.
2. **Jog** Z− in 10 → 2 → 0.5 mm steps until the (imaginary) pen kisses the
   (imaginary) paper. Watch the live `z:` readout.
3. **Use current Z** → the Table Z field fills with the live Z.
4. **Save** → `drawing.json` now holds it; verify with `uarm pen show`.

On the real arm this is the whole pen-height calibration, done from a phone
or laptop next to the robot.

## 4. Grid dry-run from the browser

With cX `250`, cY `0`, cell `40`, press **Jog corners**.

**Expected:** the 3D arm visits the four grid corners — `(190,−60) →
(190,60) → (310,60) → (310,−60)` — and loops back to the first, all at
pen-up height with straight corner-to-corner edges, then a success toast.
The pen never lowers.

Set cell to `200` and press it again. **Expected:** an error toast — "4 grid
corner(s) unreachable at pen-up Z … Move/shrink the grid." — and **no
motion at all**.

## What you should NOT see yet (deferred)

- **No live `table_z` preview in the viz** while jogging — the trace plane
  only updates when an activity starts or shapes are drawn.
- **No feed fields in the tic-tac-toe / draw-shapes widgets** — per-run feed
  overrides stay CLI-only (`-o feed=…`); the panel sets the persisted values.
- **No interactive Z-jog buttons inside the Pen section** — use the existing
  Jog section; the panel only captures the result.
