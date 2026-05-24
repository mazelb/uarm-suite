# uArm Suite — Phase 3 kickoff prompt (fresh session)

Paste everything below the divider into a new session. It assumes the standard
kickoff checklist in `CLAUDE.md` (read it, check the last commit, run the test
suite, ask before coding).

---

We're continuing work on the uArm Swift control suite. Start by reading
`CLAUDE.md` end-to-end — geometry constants, the IK derivation, the j1/j2
convention (both segments use **absolute angles from horizontal**, not elbow
bend), joint limits and the parallelogram coupling `j2 > 2·j1 − 180°`, the
hard rules, and the six-phase roadmap. Then read
`docs/walkthroughs/phase2.md` so you know the CLI behaviors you'll be
streaming to the viz. Confirm green state before writing any code:

```bash
git log --oneline -5
uv run pytest -v
uv run ruff check .
```

You should see two commits (`Phase 1: kinematics + config + tests` and
`Phase 2: sim bus + UArm class + CLI`), 51 tests passing, lint clean.

## Where we are

Phases 1–2 are committed. Repo contents:

```
uarm-suite/
├── CLAUDE.md
├── pyproject.toml          uv project; setuptools build; py311+; pytest+hypothesis+ruff+typer
├── conftest.py             adds repo root to sys.path for the flat layout
├── config.py               geometry, joint limits, channel map, servo calibration, motion defaults
├── kinematics.py           FK/IK (elbow-up only), WorkspaceError, JointLimitError
├── hardware.py             ServoBus protocol, SimulatedBus (50 Hz tick, slewing, listeners),
│                           PCA9685Bus stub, make_bus() factory
├── arm.py                  UArm class: motion, recording/replay, position callbacks, pump/gripper stubs
├── cli.py                  Typer CLI: home, goto, joints, where, record, play, list, shell
├── tests/
│   ├── test_kinematics.py  20 tests
│   ├── test_arm.py         18 tests
│   └── test_cli.py         13 tests
└── docs/
    ├── prompts/
    ├── reports/phase2.md
    └── walkthroughs/
        ├── phase1.md
        └── phase2.md
```

## Lessons from Phase 2 (read before coding)

These issues came up during Phase 2. Be aware of them so you don't repeat
the same mistakes or rely on assumptions that turned out wrong.

1. **SimulatedBus initial channel state.** The first implementation set
   `_current[channel] = degrees` on first `set_angle`, which skipped the
   slew entirely (current == target from the start). This was fixed to
   initialize channels to 0.0. **Implication for Phase 3:** the viz will
   show the arm starting at the fully-extended horizontal pose
   `(0, 0, 0, 0)` until `home()` or a motion command is issued. The
   WebSocket stream will show the slew from initial to target.

2. **Click/Typer negative argument parsing.** `-30` as a positional arg
   is interpreted as option flag `-3`. Fixed with
   `context_settings={"ignore_unknown_options": True}`. Not relevant to
   Phase 3 (FastAPI), but worth knowing if you add CLI commands.

3. **FK round-trip tolerance is ~1.5 mm** after IK → bus → FK. Tests use
   `abs=1.5` for Cartesian position assertions. The viz should not depend
   on sub-mm precision.

4. **Each CLI invocation creates its own UArm.** There is no shared server
   or persistent process yet. **This is the core problem Phase 3 solves:**
   the FastAPI server holds a single persistent `UArm` instance, and both
   the CLI (via HTTP/WebSocket) and the viz connect to it.

5. **Phase 1 mirror-IK TODO** (`kinematics.py:143`) — IK mirror solutions
   when `j1 > 90°`. Still present, still not a blocker. Don't try to fix
   it in Phase 3.

6. **`set_speed()` was added to ServoBus protocol.** The Phase 2 kickoff's
   minimal protocol didn't include it, but speed control was needed for
   `home()` and `--speed` options. The server should use the same speed
   API when forwarding motion commands.

## What to do in Phase 3

Per CLAUDE.md, Phase 3 is "server.py + 3D viz (sim only, read-only)."
**Done when:**

- `uv run python server.py` starts a FastAPI server (default port 8000).
- A WebSocket at `ws://localhost:8000/ws` streams sim state as JSON at
  the bus tick rate (~50 Hz).
- Opening `http://localhost:8000/` in a browser shows a 3D visualization
  of the arm rendered with Three.js.
- Driving the arm from a **second terminal** via CLI (e.g.,
  `uv run uarm goto 250 0 50`) causes the 3D arm to animate in real time.
- Phase 3 is **read-only** — no controls in the browser. The viz just
  watches.
- All tests green (`uv run pytest`).
- Walkthrough, build report, and next-phase kickoff prompt committed.
- Sub-agent validation passes.

### Key architectural change: shared UArm instance

The current CLI creates a fresh `UArm()` per invocation. For Phase 3, the
server needs a persistent `UArm` instance that both the WebSocket stream
and CLI commands share. Two approaches:

**Option A — Server owns the arm; CLI talks to server.**
The server holds the singleton `UArm`. CLI commands send HTTP requests to
the server instead of creating their own bus. This is the clean long-term
architecture but requires refactoring `cli.py` to use `httpx` or similar.

**Option B — Shared bus via multiprocessing or file.**
Both server and CLI create their own `UArm` instances but share state
through a shared `SimulatedBus` (e.g., via shared memory, a Unix socket,
or a file). More complex, less clean.

**Recommended: Option A.** Add a `--server` flag or auto-detect: if a
server is running at `localhost:8000`, CLI sends commands there; otherwise
falls back to direct bus access. This keeps standalone CLI working without
a server (Phase 2 behavior preserved) while enabling the shared-instance
workflow.

Pick the approach you think is cleanest and document the choice in the
build report. The CLI must still work standalone (no server required) for
backward compatibility with Phase 2 behavior.

### `server.py`

- Use **FastAPI** with **uvicorn** (`uv add fastapi uvicorn[standard]`).
- Single persistent `UArm` instance created at server startup. Connect
  and home on startup.
- **REST endpoints** (thin wrappers over `UArm` methods):
  - `GET /api/state` — current joint angles + position (snapshot).
  - `POST /api/home` — trigger home.
  - `POST /api/goto` — body: `{x, y, z, wrist?, speed?}`.
  - `POST /api/joints` — body: `{j0, j1, j2, j3, speed?}`.
  - `GET /api/where` — same as `/api/state` (alias for discoverability).
  - Error responses: `WorkspaceError` / `JointLimitError` → 422 with the
    error message in the JSON body.
- **WebSocket endpoint** `ws://localhost:8000/ws`:
  - On connect, subscribe to the arm's position callback.
  - Stream JSON frames: `{"j0": ..., "j1": ..., "j2": ..., "j3": ...,
    "x": ..., "y": ..., "z": ...}`.
  - Throttle to ~50 Hz (match `SIM_UPDATE_HZ`).
  - Multiple clients can connect simultaneously.
- **Static file serving:** mount `static/` at `/` so `index.html`, `viz.js`,
  and `style.css` are served directly.
- Rule 6: **FastAPI handlers must not block.** Use `async def` for
  endpoints. `set_position` and `move_along` return immediately
  (non-blocking by default). `home` can use `blocking=True` in a
  background task or thread pool if needed.

### `static/index.html`

- Minimal HTML shell that loads Three.js from CDN and `viz.js`.
- No build step. Vanilla JS.
- Dark background, centered viewport.

### `static/viz.js`

- Three.js scene with a 3D arm model:
  - **Base:** cylinder on the table plane, rotates around Y axis (maps
    to `j0`).
  - **Upper arm (L1):** rectangular beam from the shoulder joint, pivots
    by `j1` (absolute angle from horizontal).
  - **Forearm (L2):** rectangular beam from the elbow, pivots by `j2`
    (absolute angle from horizontal — **not** relative to upper arm).
  - **Tool (L_TOOL):** short horizontal extension from the wrist.
  - **Joints:** small spheres or cylinders at J1, J2, J3 pivot points.
  - **Ground plane:** subtle grid for spatial reference.
- Use the geometry constants from `config.py` (hardcode them in JS — they
  won't change at runtime): `H_BASE=80, L1=142, L2=158, L_TOOL=56`.
- Connect to `ws://localhost:8000/ws` on page load.
- On each WebSocket message, update joint rotations in the scene.
- OrbitControls for camera (rotate/zoom/pan with mouse).
- Display current joint angles and position as an overlay (small text
  panel in a corner).

**Critical: get the joint conventions right.**
- `j0` rotates the entire arm about the vertical (Y in Three.js if Y-up).
- `j1` is the upper-arm's absolute angle from horizontal. `j1=0` means
  the upper arm points forward; `j1=90` means straight up.
- `j2` is the forearm's absolute angle from horizontal (NOT relative to
  upper arm). `j2=0` is forearm horizontal; `j2=90` is forearm pointing
  up; `j2<0` is forearm pointing down.
- The parallel-linkage convention means both `j1` and `j2` are set
  independently in world space — they don't compose like a serial chain.
- `j3` rotates the wrist. Optional for Phase 3 — can display but not
  critical.

### `static/style.css`

- Minimal: dark body background, full-viewport canvas, info overlay
  styling.

### Tests

- `tests/test_server.py`:
  - Use `httpx.AsyncClient` with FastAPI's `TestClient` or ASGI transport.
  - Test REST endpoints: `/api/state` returns valid JSON with expected
    keys, `/api/goto` success + error paths, `/api/home` works,
    `/api/joints` works.
  - Test WebSocket: connect, receive at least one frame, verify it has
    the expected keys (`j0`, `j1`, `j2`, `j3`, `x`, `y`, `z`).
  - Verify `WorkspaceError` → 422 response.
- **Do NOT test the JavaScript.** The viz is manually verified via the
  walkthrough.

### CLI integration (if doing Option A)

If you add server-aware CLI, update `tests/test_cli.py` to verify that
standalone mode (no server) still works identically to Phase 2. Add a
small test that verifies the CLI detects a running server (mock the
HTTP check).

## Working agreement

- `uv` for deps (`uv add`, `uv run`). `pytest` after every meaningful
  change. `ruff check --fix .` and `ruff format .` before declaring done.
- **No frontend build step.** Vanilla JS, CDN Three.js.
- **UARM_MODE defaults to sim.** No hardware in this phase.
- Type-hint everything in Python. No silent clamping.
- One commit at the end: `Phase 3: FastAPI server + 3D visualization`.

## Deliverables required at the end of Phase 3

### 1. `docs/walkthroughs/phase3.md`

Cover at minimum:

- `uv run pytest -v` (all tests green, current count).
- `uv run python server.py` — server starts, prints URL.
- Open `http://localhost:8000/` in a browser — describe what the viz
  shows (arm at initial pose, grid, dark background).
- In a second terminal: `uv run uarm goto 250 0 50` — describe what
  happens in the viz (arm animates to the new pose).
- `uv run uarm home` from the second terminal — viz shows slow-home.
- REST API spot-checks: `curl http://localhost:8000/api/state`,
  `curl -X POST http://localhost:8000/api/goto -H 'Content-Type: application/json' -d '{"x": 250, "y": 0, "z": 50}'`.
- Error path: `curl` a goto to an unreachable target — 422 response.
- WebSocket: `websocat ws://localhost:8000/ws` (if available) or describe
  the browser console network tab showing WS frames.
- "What you should NOT see yet" — no controls (sliders, buttons), no
  recording panel. Those are Phase 4.

### 2. `docs/reports/phase3.md`

Same structure as Phase 2's report: what was built, test results, drifts,
open questions, commit hash.

### 3. `docs/prompts/phase4_kickoff.md`

Prepare the Phase 4 kickoff prompt. Start with any issues or blockers
from this phase's report, then lay out the Phase 4 scope (web UI controls:
joint sliders, Cartesian jog, go-to-position form, teach/replay panel).

### 4. Phase 3 commit

One commit: `Phase 3: FastAPI server + 3D visualization`.

## Final validation — sub-agent test pass

Same pattern as Phase 2. After everything is committed, spawn **three
sub-agents in parallel**:

### Agent A — Test & lint runner (subagent_type: `general-purpose`)

```
You are validating Phase 3 of the uArm Swift control suite.

Run, in order:
  1. uv run pytest -v
  2. uv run ruff check .
  3. uv run ruff format --check .

Report:
  - Total tests collected, passed, failed, skipped, xfailed.
  - Any hypothesis flaky-test warnings.
  - Any ruff findings (file:line + rule).
  - Any format diff (file list only).

Do not fix anything. Under 300 words. Plain text, no emoji.
```

### Agent B — Walkthrough verifier (subagent_type: `general-purpose`)

```
You are validating Phase 3 of the uArm Swift control suite by
executing the manual walkthrough.

Open docs/walkthroughs/phase3.md. For every fenced bash block in
order, run the command verbatim and capture stdout+stderr. Compare
the actual output against the documented expected output line by
line. Skip steps that require a browser (note them as
"manual: browser required").

For server-dependent steps, start the server in the background
first (uv run python server.py &), wait for it to be ready, run the
curl/CLI commands, then kill the server.

Report:
  - For each step: PASS, DIVERGE (with diff), or SKIPPED (with
    reason).
  - Total step count and PASS count.

Do not modify any files. Do not retry failed commands. Under 500
words.
```

### Agent C — Hard-rules auditor (subagent_type: `general-purpose`)

```
You are auditing Phase 3 of the uArm Swift control suite against
the hard rules in CLAUDE.md.

Read CLAUDE.md "Hard rules" section (rules 1-10) and "What NOT to
do" section. Then read server.py, static/viz.js, static/index.html,
and grep through tests/ for any test that might violate the rules.

For each rule, report PASS or FAIL with file:line evidence.

Specifically verify:
  - Rule 1: no top-level imports of hardware libraries.
  - Rule 2: UARM_MODE defaults to sim.
  - Rule 5: WorkspaceError/JointLimitError are surfaced as 422,
    not swallowed.
  - Rule 6: FastAPI handlers don't block on long moves.
  - No frontend build step (CDN Three.js, vanilla JS).
  - No Docker, no microservices.
  - No auth, no database.

Do not modify any files. Under 400 words.
```

After all three return, write a status block and stop. Don't start
Phase 4.

---

## Stop conditions

- Stop and ask Maz if:
  - Any hard-rule audit fails.
  - You find a regression in Phase 1 or 2 code.
  - You're about to deviate materially from the plan.
  - You want to add a dep beyond `fastapi` and `uvicorn`.
  - The viz joint conventions look wrong (this is the #1 thing Phase 3
    is meant to catch — if the arm looks wrong in 3D, say so).
- **Do not** start Phase 4. Stop after the sub-agent validation block.
