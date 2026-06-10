# Phase 8B walkthrough — Straight-line drawing at a real feed rate

Step-by-step manual validation for Phase 8B. Everything here runs in **sim
mode** (`UARM_MODE=sim`, the default) — no hardware required. The feed *values*
only mean something on paper; this walkthrough proves the *machinery* so that
on the Pi, tuning is just `uarm pen set --feed …` between test scribbles.

## What 8B delivers

Before 8B, drawing moved vertex-to-vertex with joint-space slews. Two problems
for ink on paper:

1. **Curved lines.** Joints interpolate linearly, the tool tip doesn't — a
   120 mm "straight" grid line actually bowed sideways.
2. **No speed control where it matters.** Speed was joint °/s; line quality
   depends on the *pen tip's* mm/s.

8B adds:

- `UArm.move_linear(x, y, z, wrist=…, feed=…, step_mm=…)` — subdivides the
  segment into ≤ 2 mm Cartesian steps (`DRAW_STEP_MM`), solves IK for **every
  step before any motion** (an unreachable midpoint refuses cleanly — the
  no-half-drawn-stroke invariant now covers midpoints, not just vertices), and
  paces the steps so the tip moves at `feed` mm/s.
- `kinematics.interpolate_line()` — the pure interpolation helper.
- All drawing (`draw-shapes`, `tic-tac-toe`) goes through `move_linear`:
  pen-down motion at the **draw feed**, pen-up travel at the **travel feed**,
  and pen *lowering* at the draw feed so the tip lands gently.
- `DrawingConfig` gains `feed` / `travel_feed` (persisted in `drawing.json`,
  `null` = suite defaults `DRAW_FEED_MM_S = 40`, `TRAVEL_FEED_MM_S = 120` in
  `config.py`). New `uarm pen set --feed / --travel-feed`.
- Activities accept `-o feed=… -o travel_feed=…` overrides per run.

## 1. Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

**Expected:** `166 passed`, `All checks passed!`.

## 2. See the feed in the config

```bash
uv run uarm pen show
```

**Expected** (no `drawing.json` yet — note the suite-default markers):

```
table_z  =    0.0 mm   (pen-down contact height)
pen_up   =   20.0 mm   (travel clearance)
pen_up_z =   20.0 mm
wrist    =    0.0 deg
feed     =   40.0 mm/s (pen down)   (suite default — tune on paper)
travel   =  120.0 mm/s (pen up)   (suite default)
pen      = (unlabeled)
(no drawing.json yet — showing defaults)
```

Now persist a tuned value and confirm the marker disappears:

```bash
uv run uarm pen set --feed 60 --travel-feed 150
uv run uarm pen show
```

**Expected:** `feed     =   60.0 mm/s (pen down)` with no "(suite default)"
note, and `drawing.json` now contains `"feed": 60.0`.

## 3. Watch a straight, paced stroke in the 3D viz

Terminal 1:

```bash
uv run uvicorn server:app --port 8000
```

Open <http://localhost:8000>. Terminal 2:

```bash
uv run uarm activity run draw-shapes -o shape=square -o size=40
```

**Expected in the viz:**

- The pen trace's square edges are **straight** — before 8B the long edges
  visibly bowed.
- Pen-down motion is noticeably **slower** than the pen-up hops between
  strokes (60 vs 150 mm/s with the step-2 values).

Re-run with a crawling feed to make the pacing unmistakable:

```bash
uv run uarm activity run draw-shapes -o shape=triangle -o feed=15
```

**Expected:** each triangle edge takes ~5 s of smooth, constant-speed motion.

## 4. Midpoint refusal (the new invariant)

A target whose *endpoints* are fine but whose connecting line leaves the
workspace must refuse before the pen moves at all. From a Python shell:

```bash
uv run python -c "
from arm import UArm
arm = UArm().connect()
arm.home(blocking=True)
arm.set_position(250, 0, 40, blocking=True)
try:
    arm.move_linear(400, 0, 40, feed=50)
except Exception as e:
    print('refused:', type(e).__name__)
"
```

**Expected:** `refused: WorkspaceError` (or `JointLimitError`, whichever limit
the line crosses first) and the arm does not move toward the target at all.

## 5. Tic-tac-toe still plays (now with feeds)

```bash
uv run uarm activity run tic-tac-toe
```

**Expected:** grid/X/O drawing is straight-line and feed-paced; the game is
otherwise unchanged. `-o feed=…` works here too.

## What you should NOT see yet (deferred)

- **No tuned feed values.** 40/120 mm/s are guesses; real values come from
  pen-on-paper testing in the hardware bring-up (8B's hardware half).
- **No web-UI pen panel.** Pen/feed settings are CLI-only; the browser panel
  is the next sim work item.
- **No acceleration ramps.** Steps are constant-feed; if the real servos jerk
  at stroke starts, trapezoidal ramping is a future tweak, not promised here.
- **`uarm goto` is unchanged** — it still does a joint-space slew (it proxies
  to the server when one is running; a `--feed` flag there is not part of 8B).
