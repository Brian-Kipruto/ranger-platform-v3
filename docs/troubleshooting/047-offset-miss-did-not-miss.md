# 047 — The 15 m "miss" completed waypoint 1: an east shift on an east-going leg

*Date: 2026-10-30*

---

## What we saw

The 6b negative: mission #11 started, `nmea_sim --route … --offset-east-m 15`. The
sim's own second line said `closest approach … wp1=4.6 wp2=4.6 wp3=15.0 wp4=5.8`, and
the DB showed `COMPLETED,PENDING,PENDING,PENDING` for 220 s. The check printed
`FAIL miss: something completed`.

## The cause

The setup, not the platform. Leg 1 ran east-south-east (~293 m east, ~93 m south).
Shifting a nearly east–west line 15 m east moves it only 15 × 93/307 ≈ 4.5 m sideways
from wp1 — inside 5 m. The platform was right on every count: wp1 was passed at
4.6 m and completed; wp2's best fix (4.6 m before jitter) landed just outside 5 m, so
it stayed PENDING, and nothing after it could complete (no skipping).

The instruction had said wp1 must read ≥ 6; the command didn't check it.

## The fix

- Abort #11; clone #10 as #12 "6b miss 2".
- Pick the offset from the sim's own preview (scratch output, not the live feed):
  the first of 20, 30, 40, 50, 60, 80 m giving wp1 ≥ 10 m.
- Gate the run on the **live** sim's closest-approach line before polling.

Result: 363 fixes, 16.1–450.4 m from wp1, nothing completed; recovery 6.1 s.

## Prevention

- A negative proof checks its own precondition in the command, not in the prose.
- Read `closest approach` before every miss run; only wp1 matters for "nothing
  completes".
- Open item: an offset perpendicular to leg 1 misses wp1 by exactly the offset on any
  geometry.
