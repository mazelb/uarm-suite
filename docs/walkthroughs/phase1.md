# Phase 1 — manual walkthrough

What you should be able to see and do after Phase 1 (kinematics + config +
tests). Everything here is pure software; no Pi, no servos, no hardware
libraries involved.

If any step diverges from the expected output, treat it as a regression
and flag it before moving on.

---

## 0. Prereqs

- WSL or Linux, Python 3.11+ available.
- `uv` will install itself in the first step below if missing.
- Working directory: `/mnt/e/Uarm-suite`.

## 1. Bootstrap the environment

```bash
cd /mnt/e/Uarm-suite
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv sync
```

**Expected:** `uv sync` resolves and installs 8 dev packages
(`hypothesis`, `pytest`, `ruff`, `pluggy`, `iniconfig`, `packaging`,
`pygments`, `sortedcontainers`) into `.venv/`. Should take a few seconds
on a warm cache; ~30 s the first time.

## 2. Run the kinematics test suite

```bash
uv run pytest tests/test_kinematics.py -v
```

**Expected:** `20 passed` in roughly 4–5 seconds. No skips, no xfails, no
warnings. The progress lines should look exactly like:

```
test_fk_fully_extended_horizontal PASSED              [  5%]
test_fk_straight_up PASSED                            [ 10%]
test_fk_upper_arm_up_forearm_horizontal PASSED        [ 15%]
test_fk_base_rotation_90 PASSED                       [ 20%]
test_fk_j3_does_not_affect_position PASSED            [ 25%]
test_ik_fully_extended_horizontal PASSED              [ 30%]
test_ik_straight_up PASSED                            [ 35%]
test_ik_passes_wrist_through PASSED                   [ 40%]
test_ik_unreachable_too_far_raises PASSED             [ 45%]
test_ik_unreachable_dead_zone_raises PASSED           [ 50%]
test_ik_joint_limit_violation_raises PASSED           [ 55%]
test_ik_j0_limit_violation_raises PASSED              [ 60%]
test_in_workspace_true_for_reachable PASSED           [ 65%]
test_in_workspace_false_for_far PASSED                [ 70%]
test_in_workspace_false_for_limit_violation PASSED    [ 75%]
test_fk_ik_roundtrip PASSED                           [ 80%]
test_ik_at_max_reach_within_tolerance PASSED          [ 85%]
test_ik_just_past_max_reach_raises PASSED             [ 90%]
test_jointangles_is_tuple_of_floats PASSED            [ 95%]
test_position_is_tuple_of_floats PASSED               [100%]
```

Two tests are worth checking in particular:

- `test_fk_ik_roundtrip` runs 200 randomized configurations through
  `forward_kinematics → inverse_kinematics → forward_kinematics` and
  verifies the position round-trips to < 0.1 mm. If only this one fails,
  the IK math regressed.
- `test_ik_joint_limit_violation_raises` confirms the parallelogram
  coupling check `j2 > 2·j1 − 180°` is still firing. If you want to
  change which targets are rejected, edit `parallelogram_floor_deg` in
  `config.py` and update this test together.

## 3. Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

**Expected:** `All checks passed!` from the first, and no diff from the
second. Both should be near-instant.

## 4. REPL spot-checks

```bash
uv run python
```

Then paste these one at a time:

```python
from kinematics import forward_kinematics, inverse_kinematics, in_workspace
from config import H_BASE, L1, L2, L_TOOL

# (a) Both segments horizontal forward: j1=j2=0
forward_kinematics(0, 0, 0)
# → Position(x=356.0, y=0.0, z=80.0)
#   L1+L2+L_TOOL = 142+158+56 = 356, base axis at z=H_BASE=80
```

```python
# (b) Arm fully extended straight up: j1=j2=90 (both segments vertical)
forward_kinematics(0, 90, 90)
# → Position(x=56.0..., y=0.0, z=380.0)
#   tool tip offset L_TOOL=56 forward; top of arm z = H_BASE+L1+L2 = 380
```

```python
# (c) L-shape: upper arm vertical, forearm horizontal (j1=90, j2=0)
forward_kinematics(0, 90, 0)
# → Position(x=214.0, y=0.0, z=222.0)
#   tip_r = L2 + L_TOOL = 214; tip_z = H_BASE + L1 = 222
```

```python
# (d) Round-trip the straight-up target through IK
inverse_kinematics(56.0, 0.0, 380.0)
# → JointAngles(j0=0.0, j1≈90.0, j2≈90.0, j3=0.0)
```

```python
# (e) Unreachable (too far): clean WorkspaceError
inverse_kinematics(500, 0, 80)
# → WorkspaceError: target (500.0, 0.0, 80.0) is 444.0 mm from shoulder;
#   max reach 300.0 mm
```

```python
# (f) Inside reach but violates parallelogram coupling: clean JointLimitError
inverse_kinematics(200, 0, 80)
# → JointLimitError: j2 = -55.86° must be > -45.87°
#   (parallelogram linkage constraint: j2 > 2·j1 − 180°, with j1 = 67.07°)
```

```python
# (g) in_workspace returns a bool (no exception leaks out)
in_workspace(250, 0, 50)   # → True
in_workspace(500, 0, 80)   # → False  (geometry)
in_workspace(200, 0, 80)   # → False  (parallelogram coupling)

exit()
```

If any of these blow up with a `TypeError`, `AttributeError`, or
unexpected exception type, that's a regression.

## 5. Confirm the geometry constants

```bash
uv run python -c "from config import H_BASE, L1, L2, L_TOOL, J1_LIMITS, J2_LIMITS, parallelogram_floor_deg; \
  print(f'H_BASE={H_BASE} L1={L1} L2={L2} L_TOOL={L_TOOL}'); \
  print(f'J1_LIMITS={J1_LIMITS} J2_LIMITS={J2_LIMITS}'); \
  print(f'parallelogram floor at j1=60°: j2 > {parallelogram_floor_deg(60.0)}')"
```

**Expected:**

```
H_BASE=80.0 L1=142.0 L2=158.0 L_TOOL=56.0
J1_LIMITS=(0.0, 135.0) J2_LIMITS=(-135.0, 90.0)
parallelogram floor at j1=60°: j2 > -60.0
```

If you've measured your physical arm and these are wrong, edit `config.py`
and re-run step 2 — every test should still pass (the IK is parameterized
on these constants).

---

## What you should NOT see yet (deferred to later phases)

- **No CLI.** `uv run uarm` will fail with "command not found" — that's
  Phase 2.
- **No hardware code actually running.** `hardware.py` doesn't exist yet;
  `PCA9685Bus` is Phase 5.
- **No web UI / 3D viz.** Phases 3 and 4.
- **No recordings, no `arm.UArm` class.** Phase 2.
