# Phase 3 — build report

## What was built

### `server.py` — FastAPI server with persistent UArm

- **Lifespan:** creates a single `UArm` instance on startup, connects and
  homes to the safe pose `(j0=0, j1=45, j2=-45, j3=0)`. Disconnects on
  shutdown.
- **REST endpoints:**
  - `GET /api/state` — snapshot of current joint angles and Cartesian position.
  - `GET /api/where` — alias for `/api/state`.
  - `POST /api/home` — triggers slow-home (30 deg/s), blocks until complete,
    returns final state. Uses `asyncio.to_thread` so the event loop stays
    responsive.
  - `POST /api/goto` — body `{x, y, z, wrist?, speed?}`. Runs IK, sends to
    bus, blocks until reached. `WorkspaceError` / `JointLimitError` → 422
    with `{"error": "..."}`.
  - `POST /api/joints` — body `{j0, j1, j2, j3, speed?}`. Same blocking +
    error pattern.
- **WebSocket `ws://localhost:8000/ws`:** streams JSON frames at ~50 Hz
  (matching `SIM_UPDATE_HZ`). Each frame contains `j0`–`j3` and `x`, `y`,
  `z`. Multiple clients can connect simultaneously. Polling approach — each
  client reads current state from the arm on its own timer, avoiding
  thread-safety issues with the bus listener callback.
- **Static files:** mounted at `/` with `html=True` so `index.html` is
  served for the root path. API routes take priority over the static mount.

### `static/` — Three.js 3D visualization

- **`index.html`:** minimal shell loading Three.js 0.162.0 from jsdelivr CDN
  via importmap. No build step.
- **`viz.js`:** ES module with the full arm model:
  - Hierarchy: `baseGroup` → `shoulderPivot` → `upperArmGroup` →
    `elbowPivot` → `forearmGroup` → `wristPivot` → `toolGroup`.
  - Joint mapping: `baseGroup.rotation.y = -j0`, `upperArmGroup.rotation.z = j1`,
    `forearmGroup.rotation.z = j2 - j1` (so forearm world angle = j2, absolute),
    `toolGroup.rotation.z = -j2` (tool stays horizontal — parallel linkage).
  - OrbitControls for camera rotation/zoom/pan.
  - WebSocket connects on page load, auto-reconnects on disconnect.
  - Info overlay shows joint angles, Cartesian position, and connection
    status.
- **`style.css`:** dark theme, monospace font, full-viewport canvas, overlay
  styling.

### CLI updates (`cli.py`)

- **Server auto-detection:** `_server_running()` checks
  `GET /api/state` on `localhost:8000` with a 0.3s timeout. Validates the
  response has expected keys to avoid false positives from unrelated servers.
- **Server-aware commands:** `home`, `goto`, `joints`, `where` forward to
  the server when it's running. Error responses (422) are displayed with the
  same `Error: ...` format as direct mode.
- **Standalone fallback:** when no server is running, all commands use a
  local `UArm` instance — identical to Phase 2 behavior.
- **Unchanged commands:** `record`, `play`, `list`, `shell` always use a
  local bus (server-side recording is deferred to Phase 4+).

### Tests

- `tests/test_server.py` — 8 tests covering all REST endpoints, error
  paths, and WebSocket streaming. Uses `TestClient` with a fast bus
  (10000 deg/s) to avoid 1.5s home delays per test.
- `tests/test_cli.py` — 1 new test (`test_where_uses_server_when_available`)
  verifying the CLI detects a running server and forwards the request.

## Test results

```
60 passed in ~26s
ruff check: All checks passed
ruff format: no diff
```

| File | Tests |
|---|---|
| `test_kinematics.py` | 20 (unchanged) |
| `test_arm.py` | 18 (unchanged) |
| `test_cli.py` | 14 (13 unchanged + 1 new) |
| `test_server.py` | 8 (new) |

## Architecture choice: Option A

**Server owns the arm; CLI talks to server.** This is the clean long-term
architecture per the kickoff prompt.

- Server holds the singleton `UArm` instance.
- CLI auto-detects: if server is reachable, forward via HTTP; otherwise
  fall back to direct bus (Phase 2 backward compatibility preserved).
- Used `urllib.request` (stdlib) for CLI→server communication to avoid
  adding a production dependency beyond `fastapi` and `uvicorn`.
- `httpx` added as a dev dependency only (required by `TestClient`).

## Drifts from plan

- **Non-blocking vs. blocking endpoints:** the kickoff suggested
  `set_position` returning immediately (non-blocking). I used
  `asyncio.to_thread(blocking=True)` instead because: (a) the CLI needs the
  final position in the HTTP response, (b) `set_joint_angles(blocking=False)`
  has a pre-existing speed reset bug (speed is set then immediately reset
  before the bus moves), and (c) `to_thread` keeps the event loop responsive
  despite the handler awaiting the move. Rule 6 compliance: the event loop
  never blocks; only the thread-pool thread waits.

## Open questions

1. **Speed parameter with non-blocking moves:** `set_joint_angles` with
   `blocking=False` immediately resets `_bus.set_speed(DEFAULT_DEG_PER_SEC)`
   after sending angles, defeating the custom speed. This pre-dates Phase 3
   and only matters for non-blocking calls with `speed != None`. Not a
   blocker; the blocking approach works correctly.

2. **Recording via server:** currently, `record` and `play` always use a
   local bus. For server-side recording (so recorded trajectories are
   visible in the viz), the server would need recording endpoints. Deferred
   to Phase 4.

3. **Three.js version pinning:** using 0.162.0 from CDN. If the CDN URL
   ever breaks, the viz won't load. A local copy could be considered for
   robustness, but that conflicts with the "no frontend build step" rule.

## Commit

`Phase 3: FastAPI server + 3D visualization`
