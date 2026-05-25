# Phase 4 Walkthrough — Web UI Controls

## Prerequisites

- Phases 1–3 committed, all tests passing.
- Python venv via `uv`.

## 1. Run tests

```bash
uv run pytest -v
```

**Expected:** 65 tests pass (20 kinematics, 18 arm, 14 CLI, 13 server).

## 2. Start the server

```bash
uv run python server.py
```

**Expected:** Uvicorn starts on `http://0.0.0.0:8000`. The arm homes to
(j1=45, j2=-45).

## 3. Open the browser

Navigate to `http://localhost:8000`.

**Expected:** 3D visualization loads with the arm in home position. The
info overlay (top-left) shows joint angles and Cartesian position. A
**Controls** panel appears on the right side with four sections: Joints,
Jog, Go To, and Teach.

## 4. Joint sliders

Drag the **J0** slider left and right.

**Expected:**
- The slider value label updates in real time (e.g., "J0 -30.0°").
- The 3D arm rotates around the base as J0 changes.
- The info overlay's j0 value and x/y coordinates update.
- Other sliders stay synced to the arm's current state.

Try dragging **J1** up (toward 90°). The arm's upper link lifts.

Try setting J1 to 80 and J2 to -30 (parallelogram violation). **Expected:**
a red toast notification appears at the bottom center showing the constraint
error, and the arm does not move to the invalid position.

## 5. Jog buttons

Set the step size to `20` mm. Click **X+**.

**Expected:** The arm moves ~20 mm along the X axis. The info overlay's
X value increases by ~20 mm. The 3D viz updates smoothly.

Click **Z+**, **Z-**, **Y+**, **Y-** to jog in those axes.

Click **X+** repeatedly toward the workspace limit. **Expected:** when the
target goes beyond the reachable workspace, a toast notification shows the
error message (e.g., "Target out of workspace").

## 6. Home button

Click the **Home** button in the Jog section.

**Expected:** The arm returns to home position (j0=0, j1=45, j2=-45, j3=0).
The button text changes to "Homing..." during the move.

## 7. Go-to-position form

Enter X=250, Y=50, Z=80, W=0 and click **Go**.

**Expected:** The arm moves to approximately (250, 50, 80). Check the info
overlay for the actual position (should be within ~2 mm).

Try entering X=500, Y=0, Z=0 and click **Go**. **Expected:** a toast
error about workspace limits.

## 8. Teach — record and replay

1. Enter "walkthrough" in the recording name field.
2. Click **Record** — the button turns red and pulses with text "Stop".
3. Use the joint sliders or jog buttons to move the arm around (a few
   positions).
4. Click **Stop** — a green "Recording saved" toast appears.
5. The **Recordings** list below now shows "walkthrough" with a Play button.
6. Click **Home** to return to home position.
7. Click **Play** next to "walkthrough".

**Expected:** The arm replays the recorded motion path. The 3D viz
animates the replay in real time.

Adjust the **Speed** field to `2.0` and replay again. **Expected:** the
replay runs at double speed.

## 9. Panel collapse

Click the **‹** button in the Controls panel header.

**Expected:** The control panel collapses, leaving only the header.
The toggle button changes to **›**. Click again to expand.

## 10. WebSocket reconnection

Stop the server (Ctrl+C). **Expected:** the info overlay status changes
to "Disconnected — reconnecting…" in red.

Restart the server. **Expected:** the status changes back to "Connected"
in green. The controls resume working.

## 11. Verify API endpoints via curl

```bash
# State includes recording flag
curl -s http://localhost:8000/api/state | python3 -m json.tool
# Should show "recording": false

# Record start
curl -s -X POST http://localhost:8000/api/record/start \
  -H "Content-Type: application/json" -d '{"name":"curl_test"}'
# {"status": "recording", "name": "curl_test"}

# Record stop
curl -s -X POST http://localhost:8000/api/record/stop
# {"status": "stopped", "path": "recordings/curl_test.json"}

# List recordings
curl -s http://localhost:8000/api/recordings | python3 -m json.tool
# Should include "curl_test"

# Replay
curl -s -X POST http://localhost:8000/api/play \
  -H "Content-Type: application/json" -d '{"name":"curl_test"}'

# Replay not found → 404
curl -s -X POST http://localhost:8000/api/play \
  -H "Content-Type: application/json" -d '{"name":"nope"}'
# {"error": "Recording 'nope' not found"}

# Joint limit validation
curl -s -X POST http://localhost:8000/api/joints \
  -H "Content-Type: application/json" -d '{"j0":0,"j1":80,"j2":-30,"j3":0}'
# 422 with parallelogram constraint error
```

## What you should NOT see yet

- No PCA9685 / hardware code is used (UARM_MODE=sim by default).
- No authentication, no database.
- No calibration wizard.
- No workspace visualization overlay on the 3D view.
