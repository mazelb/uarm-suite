# Phase 2 — manual walkthrough

What you should be able to see and do after Phase 2 (sim bus + UArm class +
CLI). Everything here is pure simulation; no Pi, no servos, no hardware
libraries involved.

If any step diverges from the expected output, treat it as a regression and
flag it before moving on.

---

## 0. Prereqs

- WSL or Linux, Python 3.11+ available.
- `uv` installed (should already be from Phase 1).
- Working directory: `/mnt/e/Uarm-suite`.

```bash
cd /mnt/e/Uarm-suite
uv sync
```

**Expected:** resolves and installs the project with typer and its
dependencies. Should be near-instant on a warm cache.

## 1. Run the full test suite

```bash
uv run pytest -v
```

**Expected:** `51 passed` in roughly 20 seconds. No skips, no xfails, no
warnings. Test files:

- `tests/test_kinematics.py` — 20 tests (unchanged from Phase 1)
- `tests/test_arm.py` — 18 tests (new)
- `tests/test_cli.py` — 13 tests (new)

## 2. Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

**Expected:** `All checks passed!` and no format diff.

## 3. CLI help

```bash
uv run uarm --help
```

**Expected:** shows 8 commands: `home`, `goto`, `joints`, `where`, `record`,
`play`, `list`, `shell`.

## 4. `uarm where` — initial position

```bash
uv run uarm where
```

**Expected:**

```
Position: (356.0, 0.0, 80.0)
Joints: j0=0.00 j1=0.00 j2=0.00 j3=0.00
```

The sim starts with all joints at 0° (both arm segments horizontal forward).
The tool tip is at `L1 + L2 + L_TOOL = 356 mm` along +X, at `z = H_BASE = 80 mm`.

## 5. `uarm home` — slow-home to safe pose

```bash
uv run uarm home
```

**Expected:**

```
Homed to (268.1, 0.0, 68.7)
Joints: j0=0.00 j1=45.00 j2=-45.00 j3=0.00
```

The home pose is `j0=0, j1=45, j2=-45, j3=0`. The slow-home rate is 30°/s,
so the command takes roughly 1.5 seconds (max delta from initial is 45°).

## 6. `uarm goto 200 0 50` — successful Cartesian move

```bash
uv run uarm goto 200 0 50
```

**Expected:**

```
Reached (200.0, 0.0, 50.0)
Joints: j0=0.00 j1=54.46 j2=-67.11 j3=0.00
```

IK solves to the elbow-up configuration. Position is within ~1 mm of the
target (FK round-trip tolerance).

## 7. `uarm goto 200 0 80` — parallelogram coupling error

```bash
uv run uarm goto 200 0 80; echo "exit: $?"
```

**Expected:**

```
Error: j2 = -55.86° must be > -45.87° (parallelogram linkage constraint: j2 > 2·j1 − 180°, with j1 = 67.07°)
exit: 1
```

The IK solution violates the parallelogram coupling `j2 > 2·j1 − 180°`. The
CLI prints a clean error and exits non-zero.

## 8. `uarm goto 500 0 80` — out-of-reach error

```bash
uv run uarm goto 500 0 80; echo "exit: $?"
```

**Expected:**

```
Error: target (500.0, 0.0, 80.0) is 444.0 mm from shoulder; max reach 300.0 mm
exit: 1
```

Target is geometrically unreachable. Non-zero exit.

## 9. `uarm joints 0 60 -30 0` — joint-space move

```bash
uv run uarm joints 0 60 -30 0
```

**Expected:**

```
Joints: j0=0.00 j1=60.00 j2=-30.00 j3=0.00
Position: (263.8, 0.0, 124.0)
```

Negative joint angles (like `-30`) work correctly — the CLI handles the
leading `-` without interpreting it as an option flag.

## 10. Recording and replay

Recording requires Ctrl-C, which cannot be fully automated in a single
shell command. Here is the full workflow:

### Step A — record

```bash
uv run uarm record demo
```

**Expected output before Ctrl-C:**

```
Recording 'demo'... press Ctrl-C to stop.
```

Wait 1–2 seconds, then press **Ctrl-C**.

**Expected:**

```
^C
Saved to recordings/demo.json
```

### Step B — list recordings

```bash
uv run uarm list
```

**Expected:**

```
demo
```

### Step C — inspect the recording file

```bash
python3 -c "import json; d=json.load(open('recordings/demo.json')); print(json.dumps(d['frames'][:2], indent=2))"
```

**Expected shape** (timestamps and exact values will vary):

```json
[
  {
    "t": 0.0001,
    "j0": 0.0,
    "j1": 0.0,
    "j2": 0.0,
    "j3": 0.0
  },
  {
    "t": 0.0501,
    "j0": 0.0,
    "j1": 0.0,
    "j2": 0.0,
    "j3": 0.0
  }
]
```

Each frame has `t` (seconds since recording start), `j0`, `j1`, `j2`, `j3`.
Samples at 20 Hz (0.05 s apart). Since no motion was commanded during the
recording, all angles are 0°.

### Step D — replay

```bash
uv run uarm play demo
```

**Expected:**

```
Replay complete.
```

The arm replays the recorded joint trajectory. Since the recording was
idle, nothing visibly moves, but the pipeline works end-to-end.

## 11. `uarm shell` — interactive REPL

```bash
uv run uarm shell
```

**Expected banner:**

```
uArm shell — `arm` is a connected UArm instance.
Try: arm.get_position(), arm.home(), arm.set_position(250, 0, 50, blocking=True)
Type exit() or Ctrl-D to quit.
>>>
```

**Sample REPL session** (type each line at the `>>>` prompt):

```python
>>> arm.get_position()
Position(x=356.0, y=0.0, z=80.0)
>>> arm.home(blocking=True)
>>> arm.get_position()
Position(x=268.1..., y=0.0, z=68.7...)
>>> arm.set_position(250, 0, 50, blocking=True)
>>> arm.get_position()
Position(x=250.0..., y=0.0, z=50.0...)
>>> arm.get_joint_angles()
JointAngles(j0=0.0, j1=54.4..., j2=-67.1..., j3=0.0)
>>> exit()
```

---

## What you should NOT see yet (deferred to later phases)

- **No web UI / 3D visualization.** `server.py` and `static/` don't exist
  yet — that's Phase 3.
- **No joint sliders, Cartesian jog, go-to-position form.** Phase 4.
- **No real hardware.** `PCA9685Bus` is a stub that raises
  `NotImplementedError` if you try to instantiate it. Phase 5 wires it.
- **No calibration wizard.** Phase 6.
- **Recording captures only the arm's own motion.** Driving the arm from a
  second terminal doesn't record — each CLI invocation creates its own UArm
  instance. Multi-process recording becomes possible with the web server in
  Phase 3+.
