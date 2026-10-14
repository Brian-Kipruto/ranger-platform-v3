# 035 — The IMU reads roll −166°, pitch +80° at rest

*Date: 2026-10-13*

---

## What we saw

First bench run of `imu_node` with the robot still:

```
roll -165.6 pitch  +79.8 · yaw    nan · heading_raw  174.0 … ·  831.72 hPa  1634.5 m
```

Steady, plausible pressure — and an attitude that says the robot is nearly
upside down and standing on its nose.

## The cause

The sensor was right; the assumption was wrong. `imu_math` assumed the 10-DOF
board lies flat, chips up, silkscreen x forward. Working back from roll/pitch,
the accelerometer read about (−0.98, −0.04, −0.17) g: 1 g magnitude (healthy),
with the board's x axis pointing almost straight down. The board was **mounted
vertically on an extrusion, header pins up, chip side facing the robot's
back**, leaning ~10°.

## The fix

The mount is configuration, not maths: `robot/config/imu_mount.json` names
which sensor axis points forward and which points up
(`{"forward": "-z", "up": "-x"}` here); left follows as up × forward, so it is
always a proper rotation. `imu_node` rotates both accelerometer and
magnetometer into the robot frame (REP-103 FLU) before any maths;
magnetometer calibration applies in the sensor frame, before the rotation. No
mount file → the node refuses to start.

Result on the robot: at rest roll +2.4, pitch −9.5 (the lean). Tip test — rear
lifted: pitch up; left lifted: roll up; right lifted: roll down; front lifted:
pitch down. All four signs correct. A unit test pins that the shipped mount
turns the first bench reading into roll +2.3, pitch −9.8.

## Prevention

- Ask how a sensor is mounted before writing its frame maths.
- After any remount: edit `imu_mount.json`, redo the four-position tip test, and
  recalibrate the magnetometer.
- An "impossible" reading with a healthy magnitude is usually a frame problem,
  not a broken sensor.
