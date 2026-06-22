# Phase 9 — Hardware setup, from a never-booted Pi to ink on paper

The complete, first-timer-friendly bring-up guide. Written for a setup where:

- **The Pi is a Pi 2 Model B v1.1** (40-pin GPIO, 4× USB, Ethernet jack,
  microSD slot, micro-USB power). This is a **quad-core ARMv7** (Cortex-A7)
  @ 900 MHz, **1 GB RAM** board — plenty for this project. It has **no built-in
  WiFi** and **no USB-C**, so headless setup uses **Ethernet**, and power is
  **micro-USB** — see the gotchas below.
- **Headless** access over **Ethernet + SSH** (no monitor/keyboard on the Pi).
- The arm is a first-gen uArm Swift (servo-based) driven via an Adafruit
  **PCA9685** 16-channel PWM driver at I²C `0x40`.

> This doc is the **authoritative, self-contained** hardware reference and
> supersedes [`phase7-hardware.md`](phase7-hardware.md) (kept only for its
> Phase 7 tic-tac-toe framing). The session plan / order of operations is
> [`docs/prompts/phase9_kickoff.md`](../prompts/phase9_kickoff.md).

> **Safety rules in force (CLAUDE.md 7–9):** slow-home (≤30°/s) is always the
> first motion; before any command that moves the arm under power, the operator
> is told exactly what runs and how the arm will move; hardware results are
> reported only as actually observed, never fabricated.

---

## 0. Gotchas specific to the 2014 Pi (read first)

| Topic | Pi 4 (what most guides assume) | **Your Pi 2 Model B v1.1** |
|---|---|---|
| Network for headless | WiFi configured at flash time | **No onboard WiFi → use Ethernet cable to your router.** (A USB WiFi dongle also works but Ethernet is simpler.) |
| Power input | USB-C, ~3 A | **micro-USB**, ~2 A (a good 2 A phone charger works) |
| OS image | 64-bit Raspberry Pi OS | **32-bit only.** The v1.1 Cortex-A7 is 32-bit; use **Raspberry Pi OS Lite (32-bit)**. In Imager pick **Raspberry Pi 2**. |
| Python | 3.11 default (Bookworm) | Bookworm 32-bit still ships **Python 3.11** ✓ (meets the project's `>=3.11`) |
| Package install | `uv sync` is fast | ARMv7 (`armv7l`) has good wheel/`uv` support; `uv sync` is reasonable here. System `pip` + piwheels also works — see §3. |
| Speed | fast | quad-core/1 GB — fine for this project. Installs take a few minutes, not painful. |

The arm *control* workload itself is light (trig + a small web server). The 3D
viz renders in your **laptop browser**, not on the Pi.

---

## 1. Flash the SD card (done on your laptop)

1. Install **Raspberry Pi Imager** from <https://raspberrypi.com/software>.
   Insert the microSD via your card reader.
2. **Choose Device** → **Raspberry Pi 2**.
3. **Choose OS** → **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (32-bit)**.
   - *Lite* = no desktop (headless). *32-bit* is mandatory on the v1.1 chip.
4. **Choose Storage** → select the microSD (double-check it's the card).
5. **Next** → **Edit Settings** (OS customisation):
   - **General:** hostname `uarm`; set username + password you'll remember
     (this guide assumes user `maz`); set locale/timezone.
     **Leave WiFi unchecked** (Ethernet).
   - **Services:** enable **SSH** → **password authentication**.
   - **Save**.
6. **Yes** to apply → confirm erase → let it **write + verify** (slow; minutes).
7. Eject the card; insert into the Pi.
8. **Plug Ethernet** from the Pi to your router, **then** plug in **micro-USB power**.
   Green LED activity = booting. First boot is slow (~2 min).
9. From your laptop terminal:
   ```bash
   ssh maz@uarm.local
   ```
   Accept the fingerprint (`yes`), enter your password.
   - If `uarm.local` won't resolve: find the Pi's IP in your router's
     device list (or your phone's network scanner) and
     `ssh maz@<that-ip>` instead.

✅ **Stage done when:** you have a shell prompt on the Pi over SSH.

---

## 2. Enable I²C on the Pi

```bash
sudo raspi-config
# → Interface Options → I2C → Yes (enable) → Finish
sudo reboot          # reconnect with ssh after ~1 min
```

After reconnecting, confirm the I²C tools exist (install if missing):

```bash
sudo apt update
sudo apt install -y i2c-tools python3-pip git
```

Do **not** wire or power the servos yet. The `i2cdetect` check in §5 is the
first time the PCA9685 needs to be connected.

---

## 3. Get the suite onto the Pi and install deps

```bash
git clone https://github.com/mazelb/uarm-suite.git
cd uarm-suite
```

**Install approach — `uv` works well on ARMv7.** The project is `uv`-native:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # if not already installed
# then, in the repo:
uv sync                                             # runtime + dev deps
# hardware driver libs (lazy-imported by PCA9685Bus) + GPIO backend:
uv add adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit RPi.GPIO
```

> **`RPi.GPIO` is required and easy to miss.** Adafruit Blinka (>8.56) no longer
> pulls it in automatically, so without it `UARM_MODE=hardware` dies with
> `ModuleNotFoundError: No module named 'RPi'` the first time it opens the bus.
> Use `uv add` (not bare `pip`) so `uv run`'s re-sync doesn't strip it back out.
> If it errors at runtime on the latest Pi OS, swap to the drop-in:
> `uv remove RPi.GPIO && uv add rpi-lgpio`.

> **Plain-pip alternative** (piwheels serves prebuilt ARMv7 wheels, no source
> builds): `python3 -m venv .venv && source .venv/bin/activate`, then
> `pip install "fastapi>=0.136.3" "typer>=0.12" "uvicorn[standard]>=0.47.0"
> adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit` and
> `pip install -e .`. Either route is fine; pick one and stick with it.

Quick sanity check **in sim mode** (no hardware touched, default `UARM_MODE=sim`):

```bash
uv run uarm goto 200 0 50    # should report reaching the target
# (plain-pip route: activate the venv, then `uarm goto 200 0 50`)
```

✅ **Stage done when:** the sim `goto` runs cleanly on the Pi.

---

## 4. Bill of materials (the physical rig)

**Core electronics**

| Item | Spec / note |
|---|---|
| Raspberry Pi (your Pi 2 Model B v1.1) | 32-bit Pi OS, I²C enabled |
| Adafruit PCA9685 16-ch driver | I²C `0x40` default, 50 Hz PWM |
| uArm Swift (1st-gen, servo) | **4-wire feedback servos** (see §5c). Standard 3-wire PWM (White=signal, Red=V+, Black=GND) in a 3-pin JST, plus a separate Orange analog-feedback wire we leave unconnected. |
| External servo PSU | **6 V, ≥5 A** (factory uArm Swift spec is **6 V 5 A 30 W**). 5 V runs but underdrives. A 2 A supply browns out under load. **Never power servos from the Pi.** |
| 4× F-F jumper wires | I²C: VCC, GND, SDA, SCL |
| Barrel/screw-terminal pigtail | PSU into the PCA9685 V+/GND block |

**Drawing rig (for the pen activities)**

| Item | Why |
|---|---|
| Felt-tip pen / thin marker | Low friction, forgiving of small Z error. Avoid ballpoints. |
| Pen mount for the tool head | 3D-printed clamp or zip-tie/rubber-band rig; depends on your tool interface. |
| **Spring/compliant pen holder (strongly recommended)** | No force feedback; the Z height *is* the pen pressure. Compliance absorbs ±mm Z error. |
| Paper + tape/clipboard | Fix it so it can't shift mid-draw. |
| Flat, level surface | In front of the base; default grid centered ~X≈250, Y≈0. |
| Calipers / ruler | To measure `H_BASE`, `L1`, `L2`, `L_TOOL` (these are estimates in `config.py`). |

---

## 5. Wiring — power OFF the entire time

> Wire everything with **no power applied** (Pi unpowered, servo PSU off/unplugged).

### 5a. I²C: PCA9685 → Pi (4 jumpers)

| PCA9685 pin | → Raspberry Pi pin |
|---|---|
| `VCC` (logic) | Pin 1 — 3.3 V |
| `GND` | Pin 6 — GND |
| `SDA` | Pin 3 — GPIO 2 (SDA) |
| `SCL` | Pin 5 — GPIO 3 (SCL) |

`VCC` powers only the PCA9685 **logic**, not the servos.

Pi 40-pin header, top-left corner = Pin 1:
```
 (1) 3.3V   [VCC]   (2) 5V
 (3) SDA    [SDA]   (4) 5V
 (5) SCL    [SCL]   (6) GND  [GND]
 ...
```

### 5b. Servo power: external PSU → PCA9685 V+ terminal block

- PSU **+** → PCA9685 **V+** screw terminal; PSU **−** → **GND** screw terminal.
- **Common ground:** on the Adafruit board the V+ GND and logic GND are common,
  so the Pin-6 jumper from 5a already ties Pi and PSU grounds together. Keep it.
  (No common ground → servos jitter or don't respond.)
- **Never** bridge V+ to any Pi 5 V pin.

### 5c. Servos → PCA9685 output channels (one at a time)

**These are 4-wire uArm feedback servos (verified on this arm):**

| Wire | Function | Where it goes |
|---|---|---|
| **Red** | V+ | middle of the 3-pin JST plug |
| **Black** | GND | one end of the 3-pin plug |
| **White** | PWM signal | other end of the 3-pin plug |
| **Orange** (separate single JST) | analog feedback (pot wiper) | **NOT connected** — tape it off |

*Verified with a multimeter:* resistance Orange↔Black sweeps smoothly as the
joint is rotated by hand (pot wiper); White does not. Red=V+/Black=GND by
universal convention (power is the center pin of the 3-pin plug).

The White/Black/Red 3-pin JST is a standard servo plug and seats directly on the
PCA9685's 3-pin channel header. On the Adafruit board the rows are
**GND (bottom) / V+ (middle) / PWM-signal (top)** — orient the plug so **Black
lands on the GND row**. Confirm the GND pin first with the meter's continuity
(beep) mode against the board's GND (it's common with the Pi-GND jumper).

| Channel | Joint | Servo |
|---|---|---|
| 0 | J0 | Base rotation (yaw) |
| 1 | J1 | Shoulder |
| 2 | J2 | Elbow |
| 3 | J3 | Wrist rotation |
| 4 | PUMP | reserved — leave empty |
| 5 | GRIPPER | reserved — leave empty |

Unsure which physical servo is which joint? Wire your best guess —
**Stage 1 (§7) verifies and corrects channel↔joint + direction.** Don't assume.

### 5d. PCA9685 address

Leave default `0x40` (no address jumpers). The code expects it.

---

## 6. First power-on bench check (no motion)

Power sequence: **servo PSU on first**, then the Pi/software. With no PWM yet the
PCA9685 outputs zero duty and the servos are **limp — support the arm by hand.**

```bash
sudo i2cdetect -y 1
```

Expect a device at **`40`** in the grid. You'll usually also see **`70`** — that's
the PCA9685's "All-Call" address (the same chip answering a second address),
not a second device. Both are normal. If `40` is absent: re-check the 4 I²C
jumpers and that VCC↔Pin 1, GND↔Pin 6, SDA↔Pin 3, SCL↔Pin 5 (a swapped SDA/SCL
is the classic miss).

✅ **Gate:** nothing moves until `0x40` shows here.

### Optional zero-risk rehearsal (mock mode, no servos driven)

Run the **real** PCA9685 code path against an in-memory fake — prints pulse
widths, drives nothing:

```bash
UARM_MODE=mock UARM_MOCK_VERBOSE=1 uv run uarm goto 250 0 50
# home defaults: J0 1500µs, J1 2000µs, J2 1000µs, J3 1500µs (identity calib)
```

---

## 7. Staged bring-up (announce each move, then observe)

Run from the Pi (in the venv). Each stage pauses for the operator's report of
what the arm physically did before advancing.

- **STAGE 0 — Bench check:** `sudo i2cdetect -y 1` shows `0x40`. (§6)
- **STAGE 1 — Servo sanity, one joint at a time, arm held by hand:**
  ```bash
  UARM_MODE=hardware uv run python server.py   # or: uvicorn via the venv
  ```
  Open `http://uarm.local:8000` from your laptop. Use the **calibration panel**
  per-joint test buttons (J@0 / +45 / −45) to confirm each servo moves the right
  joint in the right direction. Set `direction` / `zero_deg` / `min_us` /
  `max_us` and **Save** → `calibration.json`.
- **STAGE 2 — Home + dry motion:** `home` (slow-home 30°/s, **first motion**),
  then a few `goto` targets at **safe height** well above the table; confirm the
  3D viz matches reality. Fix IK/calibration sign issues here.
- **STAGE 3 — Geometry check:** measure the real arm; update `H_BASE`, `L1`,
  `L2`, `L_TOOL` in `config.py`; re-run `uv run pytest -q` (FK/IK round-trip)
  and re-verify `goto` accuracy at known points.
- **STAGE 4 — Pen mount + contact Z:** mount the pen, jog down over paper to
  find the Z where it just touches → that's the pen `table_z`
  (`uarm pen calibrate` or the browser pen panel). Verify the grid corners are
  reachable at **pen-up** height first (no drawing).
- **STAGE 5 — First ink:** draw the grid, then a draw-shapes square; tune
  `feed` / `travel_feed` for clean lines. Watch for: skipped ink (too fast),
  blobbing at vertices (pen-down feed too slow), dragging (table_z too deep).
- **Goal:** a full tic-tac-toe game on paper against a human.

### Power-off / E-stop

- **E-stop:** `Ctrl+C`. The bus `close()` zeros every channel's duty and deinits
  I²C, cutting servo drive on shutdown (`hardware.py`, `PCA9685Bus.close`).
- Don't start drawing at `table_z = 0` (model tip plane); a mounted pen extends
  below it. Find real contact Z in Stage 4 first.

---

## 8. Tuned values to record here (fill in during bring-up)

Capture these as you go so re-rigging later is repeatable. (`calibration.json`
and `drawing.json` are per-machine and gitignored — this table is the durable copy.)

| What | Value | Notes |
|---|---|---|
| Servo 0 (J0) zero_deg / dir / min_us / max_us | | |
| Servo 1 (J1) zero_deg / dir / min_us / max_us | | |
| Servo 2 (J2) zero_deg / dir / min_us / max_us | | |
| Servo 3 (J3) zero_deg / dir / min_us / max_us | | |
| `H_BASE` / `L1` / `L2` / `L_TOOL` (measured) | | mm |
| Pen `table_z` (per pen) | | mm; label the pen |
| `feed` / `travel_feed` | | mm/s |

---

## 9. Bring-up findings (observed live, first power-on)

Real gotchas hit during the first hardware bring-up — check these before
re-deriving them:

1. **`RPi.GPIO` missing** → `ModuleNotFoundError: No module named 'RPi'` on the
   first `UARM_MODE=hardware` command. Blinka stopped auto-installing it. Fix in
   §3 (`uv add RPi.GPIO`).
2. **Servo power is the most likely "nothing moves" cause.** I²C and commands
   work off the Pi's 3.3 V, so the arm can pass `i2cdetect` and accept commands
   while the servos sit dead for lack of V+. Always confirm **~6 V across the
   PCA9685 V+/GND terminals** with a meter before suspecting software.
3. **The CLI is transient — use the server to actually drive.** `uarm joints …`
   writes the pose then exits, and `close()` zeros every channel on the way out,
   so servos barely twitch. For real motion run the **persistent server**
   (`UARM_MODE=hardware uv run python server.py`); its 50 Hz tick streams PWM
   continuously so servos hold and move. The server **auto-homes on startup**
   (slow-home 30°/s) — that first motion is expected; keep a hand on the arm.
4. **Trust a known-good meter.** A flaky meter / broken probe lead produced
   false `0 V` readings that looked like dead PSUs. Sanity-check the meter on a
   AA battery (~1.5 V) and by shorting the probes (continuity beeps) before
   trusting any reading.
5. **Undersized PSU browns out.** A 5 V 2 A adapter is ~4× too small; it may
   gently move one servo but sags/resets under multi-servo load. Use 6 V ≥5 A.
6. **All four servo directions came out reversed** (`direction = -1`) on this
   arm — normal; the servo horns are mounted opposite to the code's positive
   convention. Flip each joint to **0** first (servo center, the pivot), *then*
   set `direction = -1`, so the flip causes no swing. J3 (wrist) direction can
   wait until a pen is mounted (it doesn't affect tool-tip XYZ).
7. **"Model looks wrong" was uncalibrated zeros, not a viz bug.** `viz.js`
   renders the documented convention correctly (upper arm at j1, forearm at
   absolute j2, tool held horizontal). When the real arm tracks direction but
   sits at different *angles*, that's the unset `zero_deg`/pulse-range — calibrate
   against **real-world references** (joint 0 = upper arm horizontal, forearm
   horizontal, base straight forward), not against the on-screen model.
