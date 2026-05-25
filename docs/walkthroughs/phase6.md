# Phase 6 walkthrough — Calibration wizard, workspace viz, soft-limit toasts

## Prerequisites

- Phases 1-5 committed and passing
- `uv run pytest -v` shows 98 tests passing

## 1. Start the server

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser.

## 2. Workspace visualization

**What you should see:**
- A translucent blue volume surrounding the arm in the 3D view
- The volume shows the reachable workspace — a torus-like sector
- The arm's current position is always inside this volume

**Test:**
1. Orbit the camera to view the workspace from different angles
2. Click **Hide Workspace** in the Controls panel → the volume disappears
3. Click **Show Workspace** → it reappears
4. Move the arm with sliders — it stays inside the volume

## 3. Soft-limit toasts

**Test joint limit warnings:**
1. Drag the **J0 slider** toward +90 or -90
2. Within 10 degrees of the limit: slider thumb turns **yellow** (warning)
3. Within 5 degrees of the limit: slider thumb turns **red** (danger)
4. Moving away from the limit returns the slider to its normal blue color

**Test parallelogram constraint warning:**
1. Set J1 to around 80 using the slider
2. Drag J2 downward toward the parallelogram limit (2 * j1 - 180)
3. When j2 approaches the limit, the J2 slider turns red and a **warning toast** appears at the bottom of the screen
4. The toast says something like "Parallelogram constraint: j2 within X.X degrees of limit"

**What you should NOT see:**
- Toast spam — warnings have a 3-second cooldown between messages

## 4. Calibration wizard

**Test reading calibration:**
1. Scroll down in the Controls panel to the **Calibration** section
2. You should see a table with J0-J3, each showing:
   - Zero deg: 90
   - Direction: +1
   - Min us: 500
   - Max us: 2500

**Test updating calibration:**
1. Change J0's zero_deg to 85
2. Click the checkmark button → toast says "Ch 0 calibration updated"
3. Verify via API: `curl http://localhost:8000/api/calibration`
   - Channel 0's zero_deg should be 85.0

**Test test buttons:**
1. Click **J0@0** → arm's base rotates to joint angle 0
2. Click **+45** → base rotates to 45 degrees
3. Click **-45** → base rotates to -45 degrees
4. Repeat for J1, J2, J3

**Test save to disk:**
1. Click **Save to disk** → toast says "Calibration saved to disk"
2. Check: `cat calibration.json` — should contain the updated values
3. Restart the server → calibration values are loaded from disk

**Test reset:**
1. Click **Reset defaults** → all values return to identity calibration
2. Toast confirms reset

## 5. Verify API endpoints

```bash
# Get calibration
curl -s http://localhost:8000/api/calibration | python3 -m json.tool

# Update channel 0
curl -s -X POST http://localhost:8000/api/calibration \
  -H 'Content-Type: application/json' \
  -d '{"channel": 0, "zero_deg": 82.5, "direction": -1}'

# Save
curl -s -X POST http://localhost:8000/api/calibration/save

# Reset
curl -s -X POST http://localhost:8000/api/calibration/reset
```

## 6. Run all tests

```bash
uv run pytest -v
```

Expected: 98 tests passing (87 from phases 1-5 + 11 new).

## What you should NOT see yet

- Hardware calibration on the Pi (Phase 6 is sim-only calibration UI)
- Tic-tac-toe game (planned for Phase 7)
