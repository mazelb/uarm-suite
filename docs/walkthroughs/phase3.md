# Phase 3 — manual walkthrough

What you should be able to see and do after Phase 3 (FastAPI server + 3D
visualization, sim only). Everything here is pure simulation; no Pi, no
servos, no hardware libraries involved.

If any step diverges from the expected output, treat it as a regression and
flag it before moving on.

---

## 0. Prereqs

- WSL or Linux, Python 3.11+ available.
- `uv` installed (should already be from Phase 1).
- Working directory: `/mnt/e/Uarm-suite`.
- A modern browser (Chrome, Firefox, Edge).

```bash
cd /mnt/e/Uarm-suite
uv sync
```

**Expected:** resolves and installs the project with typer, fastapi,
uvicorn, and their dependencies. Should be near-instant on a warm cache.

## 1. Run the full test suite

```bash
uv run pytest -v
```

**Expected:** `60 passed` in roughly 25 seconds. No skips, no xfails, no
warnings. Test files:

- `tests/test_kinematics.py` — 20 tests (unchanged from Phase 1)
- `tests/test_arm.py` — 18 tests (unchanged from Phase 2)
- `tests/test_cli.py` — 14 tests (13 from Phase 2 + 1 new server detection test)
- `tests/test_server.py` — 8 tests (new)

## 2. Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

**Expected:** `All checks passed!` and no format diff.

## 3. Start the server

Open a terminal and run:

```bash
uv run python server.py
```

**Expected output (approximate):**

```
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

The server creates a `UArm` instance, connects, and homes to
`(j0=0, j1=45, j2=-45, j3=0)`. The startup takes ~1.5 seconds because of
the slow-home at 30 deg/s.

Leave this terminal running for the remaining steps.

## 4. Open the 3D visualizer

Open `http://localhost:8000/` in a browser.

**Expected:** a dark background with a grid floor and a 3D arm model:

- A grey cylindrical base sitting on the grid.
- A blue upper arm tilted ~45 deg up from horizontal.
- A green forearm angled ~45 deg down from horizontal (elbow-up configuration).
- An orange tool extension at the wrist, pointing horizontally.
- Yellow spheres at each joint pivot point.
- A red sphere at the tool tip.
- An info overlay in the top-left corner showing joint angles and position:
  - `j0: 0.00`, `j1: 45.00`, `j2: -45.00`, `j3: 0.00`
  - `x: 268.1`, `y: 0.0`, `z: 68.7`
  - Status: `Connected`

You can orbit (left-click drag), zoom (scroll), and pan (right-click drag)
the camera using mouse controls.

## 5. Drive the arm from a second terminal

Open a **second terminal** and run:

```bash
uv run uarm goto 250 0 50
```

**Expected CLI output:**

```
Reached (250.0, 0.0, 50.0)
Joints: j0=0.00 j1=54.46 j2=-67.11 j3=0.00
```

**Expected in the browser:** the 3D arm animates smoothly from the home
pose to the new position. The upper arm tilts higher and the forearm
angles further down. The info overlay updates in real time to show the
final joint angles and position.

## 6. Home from the second terminal

```bash
uv run uarm home
```

**Expected CLI output:**

```
Homed to (268.1, 0.0, 68.7)
Joints: j0=0.00 j1=45.00 j2=-45.00 j3=0.00
```

**Expected in the browser:** the arm slowly returns to the home pose at
30 deg/s. The slow-home animation takes ~1 second.

## 7. Drive with base rotation

```bash
uv run uarm goto 250 100 50
```

**Expected CLI output:**

```
Reached (250.0, 100.0, 50.0)
Joints: j0=21.80 j1=53.25 j2=-65.91 j3=0.00
```

**Expected in the browser:** the arm rotates toward the viewer (positive
j0) and reaches the target. The base cylinder turns and the arm extends
at an angle.

## 8. Joint-space move

```bash
uv run uarm joints 0 60 -30 0
```

**Expected CLI output:**

```
Joints: j0=0.00 j1=60.00 j2=-30.00 j3=0.00
Position: (263.8, 0.0, 124.0)
```

**Expected in the browser:** the arm moves to a higher pose — the upper
arm steeper, the forearm less steep.

## 9. REST API spot-checks

### State endpoint

```bash
curl http://localhost:8000/api/state
```

**Expected:** JSON with `j0`, `j1`, `j2`, `j3`, `x`, `y`, `z` keys.
Values match the last CLI command's output.

### Goto via REST

```bash
curl -X POST http://localhost:8000/api/goto \
  -H 'Content-Type: application/json' \
  -d '{"x": 200, "y": 0, "z": 50}'
```

**Expected:** JSON response with the final joint angles and position:

```json
{"j0":0.0,"j1":54.46,"j2":-67.11,...}
```

(Exact values may have minor floating-point differences.)

The browser shows the arm moving to the new position.

### Error path — unreachable target

```bash
curl -s -o - -w "\nHTTP %{http_code}\n" \
  -X POST http://localhost:8000/api/goto \
  -H 'Content-Type: application/json' \
  -d '{"x": 500, "y": 0, "z": 80}'
```

**Expected:**

```json
{"error":"target (500.0, 0.0, 80.0) is 444.0 mm from shoulder; max reach 300.0 mm"}
HTTP 422
```

### Where alias

```bash
curl http://localhost:8000/api/where
```

**Expected:** same response as `/api/state`.

## 10. WebSocket verification

### Browser DevTools

In the browser, open DevTools (F12) → Network tab → WS filter. You should
see a WebSocket connection to `/ws` with frames arriving at ~50 Hz. Each
frame is a JSON object like:

```json
{"j0":0.0,"j1":54.46,"j2":-67.11,"j3":0.0,"x":200.0,"y":0.0,"z":50.0}
```

### Command-line (if websocat is available)

```bash
websocat ws://localhost:8000/ws | head -3
```

**Expected:** three JSON frames on separate lines, each with `j0`–`j3`
and `x`–`z` fields.

## 11. Standalone CLI (no server)

Stop the server (Ctrl-C in the first terminal). Then:

```bash
uv run uarm where
```

**Expected:**

```
Position: (356.0, 0.0, 80.0)
Joints: j0=0.00 j1=0.00 j2=0.00 j3=0.00
```

The CLI falls back to a local SimulatedBus when no server is running.
This is identical to Phase 2 behavior — all Phase 2 walkthrough steps
still work without a server.

---

## What you should NOT see yet (deferred to later phases)

- **No controls in the browser.** No sliders, buttons, input fields, or
  panels. Phase 3 is read-only — the viz just watches. Controls are Phase 4.
- **No recording/replay panel.** Phase 4.
- **No real hardware.** `PCA9685Bus` is still a stub. Phase 5.
- **No calibration wizard.** Phase 6.
