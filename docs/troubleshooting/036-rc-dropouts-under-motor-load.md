# 036 — RC dropouts under motor load

*Date: 2026-10-19*

---

## What we saw

Driving above about 90 PWM, the Uno kept stopping: `X` with `rc_age=100` every
100–200 ms, and every ~300 ms at full power. Below ~90 PWM, none.

## The cause

Motor brush noise conducted through the BTS7960 drivers into the receiver's PPM
signal. It happens at a constant 255 (so it isn't PWM switching) and is unchanged
with the wires moved 10 cm away (so it isn't radiated pickup near the leads).

First suspected: the receiver sharing breadboard 5 V/GND with the BTS7960 logic.
Moving it to the Uno's IOREF and the GND by D13 made **no difference**.

## The fix

Pending: a **100 nF ceramic capacitor across each motor's terminals** (salvaged "104"
caps will do). Then rerun the 5/5/5/5 drive pattern and compare `ppm_glitches` in the
`S` line.

## Mitigation in place

The PPM filters (ADR-0022) turn the noise into **stops, never commands**: two-frame
agreement rejects corrupted in-range frames. `uno_bridge` caps `max_pwm` at **120**
until the caps are in. A longer RC-loss timeout (250 ms) was tried and rejected: it
didn't ride through the noise and slowed every real TX-loss stop.

## Prevention

- Fit suppression capacitors on brushed motors before the first powered drive.
- Watch `ppm_glitches` and `ppm_disagreed` in `S` lines whenever the drive train
  changes.
