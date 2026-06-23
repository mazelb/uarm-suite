# Phase 10 kickoff — hardware polish (after first tic-tac-toe on the real arm)

## Where we are

**Phase 9 hit its goal:** the arm is wired, calibrated, and **played a full
tic-tac-toe game on paper against a human** — first ink on the real hardware.
Everything below is "make it solid," not "make it work."

Hardware in use:
- **Raspberry Pi 2 Model B v1.1** (ARMv7, 32-bit Pi OS, headless over Ethernet,
  hostname `uarm`). `uv`-native; `RPi.GPIO` installed.
- Adafruit PCA9685 at I²C `0x40`. uArm Swift first-gen, **4-wire feedback
  servos** (White=signal, Red=V+, Black=GND, Orange=feedback **left
  disconnected**).
- **Temporary 5 V 2 A supply** — undersized, browns out under load. **Replace
  with 6 V ≥5 A** (factory spec is 6 V 5 A; see below).

Calibration (`calibration.json`, gitignored — durable copy is
`docs/walkthroughs/phase9-hardware-setup.md` §9):

| Servo | zero_deg | dir | min_us | max_us |
|---|---|---|---|---|
| J0 | 90 | −1 | 500 | 2500 |
| J1 | 75 | +1 | 500 | 2500 |
| J2 | 20 | −1 | 500 | 2500 |
| J3 | 90 | −1 | 500 | 2500 |

`min_us`/`max_us` are defaults (scale verified roughly correct). The full
calibration mental model + diagnosis table is **phase9-hardware-setup.md §7**;
read it before touching calibration.

## Deferred to this phase (rough value order)

1. **Buy + fit the 6 V ≥5 A PSU.** Biggest reliability win; current 2 A sags
   under multi-servo load (resets, stutter).
2. **Measure real joint limits → update `J*_LIMITS` in `config.py`.** Today's
   limits are estimates and don't match this arm. With the current zeros the
   servo clamps (silently!) before some limits — e.g. J1 tops out ~105°, J2
   positive ~+20° (servo hits 0/180). Jog gently to each real stop, back off a
   few degrees, set the limits to match. The parallelogram rule
   `j2 > 2·j1 − 180` is real physics — leave it. (Re-run `uv run pytest -q`.)
3. **Re-measure geometry** `H_BASE` / `L1` / `L2` / `L_TOOL` (still estimates
   80/142/158/56 mm). Makes `goto` true millimeters; fixes any grid skew/scale.
   Update `config.py`, re-run the FK/IK round-trip tests, record in §9.
4. **Drawing-quality tuning** — pen `table_z` per pen, `feed` / `travel_feed`
   for clean lines (skipped ink = too fast; blobs = pen-down feed too slow;
   dragging = table_z too deep). Record in §9.
5. **Close out the phase** — write `docs/walkthroughs/phase9.md` (or extend it)
   with what shipped + lessons; this kickoff is the lessons source.

## Rules still in force
CLAUDE.md 7–9: slow-home first; announce any powered move before running; report
only observed hardware results, never fabricated. Hardware-touching code may run
without a per-command go, but announce arm motion first.

## Hard-won bring-up lessons (don't rediscover)
See **phase9-hardware-setup.md §10** — the short version: servo power vs software
is the first thing to check when "nothing moves"; the CLI is transient (use the
persistent server to actually drive); trust a known-good meter; servo directions
came out reversed; "model looks wrong" was uncalibrated zeros, not a viz bug.
