# Phase 7 hardware bring-up — tic-tac-toe on the real arm

Guide for taking the (sim-validated) Phase 7 tic-tac-toe activity onto the
physical uArm Swift. Contains a fresh-session prompt and the hardware + wiring
reference.

## Read this first — two honest caveats

1. **The motion stack is ready to bring up; pen-drawing tic-tac-toe is not fully
   ready.** There is no automated pen-contact-Z calibration yet — that's Phase 8
   (see `docs/prompts/phase8_kickoff.md`). To draw, you set `GridConfig.table_z`
   to a height you find by hand. Treat this as a **staged bring-up**, not a
   one-shot run.
2. **Confirm your arm uses standard 3-wire PWM servos** (signal / V+ / GND). The
   whole PCA9685 approach assumes that. If the first-gen Swift's servos are
   serial-bus type, PWM won't drive them and the wiring changes entirely. Verify
   before buying or wiring anything.

Per `CLAUDE.md` rules 8 and 9: hardware testing is active — hardware-touching code
may be run without a per-command "go", but any command that moves the arm under
power is announced first (what it runs, how the arm moves); results are reported
truthfully, never fabricated.

## Stage −1 — Dry run on the dev box (no Pi, no risk)

Before any wiring, vet the real driver code path with **mock hardware mode**
(`mockhw.py`). `UARM_MODE=mock` builds the actual `PCA9685Bus` against an
in-memory fake PCA9685 — same PWM duty math, slew loop, and calibration
conversion that will run on the Pi — and prints the servo pulses:

```bash
UARM_MODE=mock UARM_MOCK_VERBOSE=1 uv run uarm goto 250 0 50
UARM_MODE=mock UARM_MOCK_VERBOSE=1 uv run python server.py   # full UI/game dry run
```

Confirm the pulse widths look sane (home → J0 1500µs, J1 2000µs, J2 1000µs,
J3 1500µs with default calibration) and the duty cycles change with the target.
This catches driver/calibration-math bugs with zero hardware risk. It does NOT
tell you whether the arm reaches a pose physically — that's what the staged
hardware run below is for.

---

## Part A — Prompt for a fresh session (paste this on the Pi)

```
We're doing the FIRST hardware bring-up of the uArm Swift on the Raspberry Pi,
working toward running the tic-tac-toe activity (Phase 7) on the real arm.

Read CLAUDE.md first. Rules 8 and 9 are in force: hardware testing is active, so
you may run hardware-touching code (I2C, GPIO, servo PWM) without waiting for a
per-command "go" — BUT before any command that moves the arm under power, state
exactly what you're about to run and how the arm will physically move. I'm
watching the arm and will tell you what actually happened; do not fabricate
results. Pure-sim commands you may run freely.

Current state: Phases 1-7 committed, 134 tests pass in sim. The PCA9685Bus exists
(hardware.py) and is selected by UARM_MODE=hardware. Servo calibration lives in
config.py SERVO_CALIBRATION and persists to calibration.json via the web UI
calibration panel. Tic-tac-toe geometry is activities/tic_tac_toe.py GridConfig
(table_z = pen contact height, currently 0 = the model's table plane).

Known gaps to handle this session:
- Geometry constants (H_BASE, L1, L2, L_TOOL in config.py) are ESTIMATES. I can
  re-measure the physical arm; help me update them.
- There is NO automated pen-Z calibration (that's Phase 8). We'll find the pen
  contact height empirically by jogging.
- The bus assumes servos start at joint 0 (servo center ~90°) on first connect;
  the first move centers the servos, so I'll support the arm by hand on power-up.

Bring it up in stages. Announce each move, then pause for my report of what the
arm actually did before advancing to the next stage:

  STAGE 0 — Bench check (no arm powered): sudo i2cdetect -y 1 shows 0x40.
  STAGE 1 — Servo sanity, one joint at a time, arm held by hand: bring up the
            server in hardware mode, use the calibration panel's per-joint test
            buttons (J@0 / +45 / -45) to verify each servo moves the right joint
            in the right direction; set direction/zero_deg/min_us/max_us and Save.
  STAGE 2 — Home + dry motion: `home`, then a few `goto` targets at SAFE height
            (well above the table), confirming the arm reaches sane poses and the
            3D viz matches reality. Fix any IK/calibration sign issues here.
  STAGE 3 — Geometry check: I measure the real arm; we update config.py and
            re-verify goto accuracy at a few known points.
  STAGE 4 — Pen mount + find contact Z: with a pen mounted, jog down over paper
            to find the Z where the pen just touches; that's GridConfig.table_z.
            Verify the four grid corners are reachable and land on the paper at
            PEN-UP height first (no drawing yet).
  STAGE 5 — Draw the grid only, then a full tic-tac-toe game with the pen.

Start at STAGE 0. Tell me the exact command and wait for my go.
```

---

## Part B — Hardware required + step-by-step wiring

### Bill of materials

**Core** (from the README, with notes):

| Item | Spec / note |
|---|---|
| Raspberry Pi 4 | Any RAM. Pi OS with I²C enabled. |
| Adafruit PCA9685 16-ch driver | I²C servo/PWM board, address `0x40` default. |
| uArm Swift (1st-gen, servo-based) | **Verify the 4 servos are standard 3-wire PWM** (see caveat above). |
| External servo PSU | **5–6 V, ≥6 A** recommended (README says 4A+; 4 metal-gear servos can spike higher under simultaneous load). Confirm your servos' rated voltage — 5 V is the safe default. |
| 4× female-female jumper wires | For I²C: SDA, SCL, VCC (3.3 V), GND. |
| Barrel-jack / screw-terminal pigtail | To wire the PSU into the PCA9685 **V+ / GND** terminal block. |

**Tic-tac-toe–specific** (the drawing rig — not in the README):

| Item | Why |
|---|---|
| Felt-tip pen / thin marker | Low friction and forgiving of small Z error. Avoid ballpoints (need downforce). |
| Pen mount/bracket for the tool head | Attaches a pen to the uArm tool tip. Exact part depends on your tool interface (suction head / gripper mount) — likely a 3D-printed clamp or a zip-tie/rubber-band rig. Can't specify the exact bracket without knowing your tool head. |
| **Spring/compliant pen holder (strongly recommended)** | No force feedback and Z is uncalibrated. A spring-loaded or foam-backed mount tolerates ±a few mm of Z error so the pen presses without the arm fighting the table. Makes drawing far more robust. |
| Blank paper + tape/clipboard | The arm draws the grid; fix the paper so it can't shift mid-game. |
| Flat, level work surface | Positioned so the paper sits within the arm's Z range and in front of the base (default grid centered around X≈250 mm, Y≈0). |
| Calipers / ruler | To measure `H_BASE`, `L1`, `L2`, `L_TOOL` (Stage 3) — currently estimates. |

### Wiring — step by step

**Power off everything before wiring. Do not power the servos from the Pi.**

**1. I²C: PCA9685 ↔ Raspberry Pi** (4 jumpers)

| PCA9685 pin | → Raspberry Pi pin |
|---|---|
| `VCC` (logic) | Pin 1 — 3.3 V |
| `GND` | Pin 6 — GND |
| `SDA` | Pin 3 — GPIO 2 (SDA) |
| `SCL` | Pin 5 — GPIO 3 (SCL) |

`VCC` powers only the PCA9685's logic — **not** the servos.

**2. Servo power: external PSU → PCA9685 `V+` terminal block**

- PSU **+** → PCA9685 **V+** screw terminal; PSU **−** → **GND** screw terminal.
- **Common ground:** on the Adafruit board the V+ terminal GND and the logic GND
  are common, so the Pi-GND-to-board-GND jumper from step 1 already ties Pi and
  PSU grounds together — keep that jumper connected. (Without a common ground the
  servos jitter or don't respond.)
- Do **not** bridge V+ to the Pi 5 V anywhere.

**3. Servos → PCA9685 output channels**

Each channel is a 3-pin header. On the Adafruit board the rows are ordered
**GND (bottom) / V+ (middle) / PWM-signal (top)**. Match your servo plug colors:

- Signal = yellow or white → **PWM** (top)
- V+ = red → **middle**
- GND = brown or black → **GND** (bottom)

Plug in **one joint at a time**, per the channel map in `config.py`:

| Channel | Joint | Servo |
|---|---|---|
| 0 | J0 | Base rotation (yaw) |
| 1 | J1 | Shoulder |
| 2 | J2 | Elbow |
| 3 | J3 | Wrist rotation |
| 4 | PUMP | reserved (stub, leave empty) |
| 5 | GRIPPER | reserved (stub, leave empty) |

If you're unsure which physical servo is which joint, that's fine — Stage 1 (the
calibration panel's per-joint test buttons) is exactly how you confirm
channel↔joint and rotation direction. Don't assume; verify each.

**4. PCA9685 config (already matches the code)**

I²C address `0x40`, 50 Hz PWM, 500–2500 µs pulse range. No change needed unless
you jumpered a different address.

### Power-on / first-connect safety (grounded in `hardware.py`)

- **Sequence:** servo PSU on first, *then* start the software. With no PWM yet the
  PCA9685 outputs zero duty and the servos are limp — **support the arm by hand**
  until the first move.
- **First move centers the servos.** The bus assumes joints start at 0 (servo
  center ≈90° with default calibration), so the first `home` ramps from center to
  the home pose at 30°/s. Keep a hand near the arm the first time.
- **E-stop:** `Ctrl+C`. The bus's `close()` zeros the duty cycle on every channel
  it touched and deinits the I²C — that cuts servo drive on shutdown
  (`hardware.py`, `PCA9685Bus.close`).
- **Don't start at the table.** The default `table_z = 0` is the *model's* table
  plane for the bare tool tip; a mounted pen sticks out below that. Find the real
  contact height by jogging down in Stage 4 before any drawing, or you'll drive
  the pen into the table.

### Software install on the Pi (recap of README)

```bash
sudo raspi-config          # Interface Options → I2C → Enable
sudo i2cdetect -y 1        # expect a device at 0x40
pip install adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit
cd uarm-suite && uv sync
UARM_MODE=hardware uv run python server.py   # hardware mode (after STAGE 0)
```
