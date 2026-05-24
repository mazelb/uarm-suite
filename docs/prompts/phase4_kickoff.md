# Phase 4 kickoff prompt

## Where we are

Phases 1–3 are committed. The repo now contains:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml
├── conftest.py
├── config.py              geometry, joint limits, channel map, servo calibration
├── kinematics.py           FK/IK (elbow-up only), WorkspaceError, JointLimitError
├── hardware.py             ServoBus protocol, SimulatedBus, PCA9685Bus stub
├── arm.py                  UArm class: motion, recording/replay, callbacks
├── cli.py                  Typer CLI (server-aware: auto-detects FastAPI server)
├── server.py               FastAPI server: REST + WebSocket, persistent UArm
├── static/
│   ├── index.html          Three.js importmap loader
│   ├── viz.js              3D arm model + WebSocket + OrbitControls
│   └── style.css           dark theme, overlay styling
├── tests/
│   ├── test_kinematics.py  20 tests
│   ├── test_arm.py         18 tests
│   ├── test_cli.py         14 tests
│   └── test_server.py      8 tests
└── docs/
    ├── prompts/
    ├── reports/
    └── walkthroughs/
```

60 tests passing, lint clean.

## Lessons from Phase 3

1. **`asyncio.to_thread` for blocking arm calls.** FastAPI handlers use
   `await asyncio.to_thread(_arm.method, blocking=True)` to keep the event
   loop responsive while waiting for the arm to reach its target. This
   pattern should continue in Phase 4 for any new endpoints.

2. **Non-blocking speed bug.** `set_joint_angles(blocking=False)` with a
   custom `speed` immediately resets `_bus.set_speed(DEFAULT_DEG_PER_SEC)`
   after sending angles, so the custom speed only lasts one tick. The
   workaround is to always use `blocking=True` in a thread. If Phase 4 adds
   jog controls that need truly non-blocking speed, this bug must be fixed
   in `arm.py` first.

3. **CLI server auto-detection.** `_server_running()` does a quick
   `GET /api/state` with a 0.3s timeout. Connection-refused returns in
   <1ms so standalone CLI performance is unaffected. New CLI commands in
   Phase 4 should follow the same pattern.

4. **Static mount at `/`.** API routes defined via decorators take priority
   over the static `StaticFiles` mount. New API endpoints added in Phase 4
   will automatically take priority without any routing changes.

5. **WebSocket is polling-based.** Each connected client polls
   `_arm.get_joint_angles()` and `_arm.get_position()` at 50 Hz in its
   own async loop. This avoids thread-safety issues with the bus listener.
   If Phase 4 adds more WebSocket data (e.g., recording state), update the
   `_state_dict()` helper or add a second WebSocket endpoint.

6. **Test fixture pattern for server tests.** `test_server.py` pre-creates
   a fast bus (10000 deg/s) and injects it via `server._arm` to avoid the
   1.5s home delay per test. Phase 4 tests should follow this pattern.

## What to do in Phase 4

Per CLAUDE.md, Phase 4 is "Web UI controls." **Done when:**

- Joint sliders (j0–j3) in the browser that drive the arm in real time.
- Cartesian jog buttons (X±, Y±, Z± step buttons) for incremental moves.
- Go-to-position form (x, y, z, wrist input fields + "Go" button).
- Teach/replay panel: start/stop recording, list recordings, replay.
- All controls drive the shared arm via the REST API — the 3D viz updates
  live.
- Error handling: workspace/joint-limit errors are surfaced in the UI (e.g.,
  toast notifications or inline error messages), not silently swallowed
  (Rule 5).
- All tests green. Walkthrough, report, and Phase 5 kickoff committed.

### UI layout suggestion

```
┌─────────────────────────────────────────────────────────────────┐
│  3D viz canvas (existing)                                       │
│                                                                 │
│                                                                 │
│  ┌──────────────┐                                               │
│  │ info overlay  │                                               │
│  │ (existing)    │                                               │
│  └──────────────┘                                               │
│                                                                 │
│                                                   ┌────────────┐│
│                                                   │ controls   ││
│                                                   │ panel      ││
│                                                   │ (new)      ││
│                                                   └────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

A collapsible panel on the right side with tabs or sections:
- **Joints** — four sliders (j0–j3) with labels and current values
- **Jog** — grid of X/Y/Z ± buttons with configurable step size
- **Go To** — x/y/z/wrist input fields + Go button
- **Teach** — Record/Stop button, recording list, Replay button

### New server endpoints needed

- `POST /api/record/start` — body `{name}` — start recording
- `POST /api/record/stop` — stop recording, return path
- `GET /api/recordings` — list recordings
- `POST /api/play` — body `{name, speed_factor?}` — replay recording

### New static files

- `static/app.js` — control panel logic (vanilla JS, no build step)
- Update `static/index.html` to load `app.js`
- Update `static/style.css` with control panel styles

### Tests

- `tests/test_server.py` — add tests for new recording/replay endpoints
- JavaScript is NOT tested — manually verified via walkthrough

### Constraints

- No frontend build step. Vanilla JS + CDN.
- No auth, no database.
- Error responses (422) must be surfaced to the user in the UI.
- `UARM_MODE` defaults to `sim`.
