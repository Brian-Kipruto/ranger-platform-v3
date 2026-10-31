# 053 — A simulated track broken 180 times

*Date: 2026-10-30*

---

## What we saw

Mission 12's report: `track_breaks: 180` on 552 fixes, and two parallel lines on the
map. The first guess was two position writers interleaved on one mission.

## The data

One writer, 1 Hz. Consecutive fixes in time order:

| kind | count | min m | avg m | max m |
|---|---|---|---|---|
| ok (≤ 5 m/s) | 371 | 0.0 | 2.7 | 5.1 |
| "jump" (> 5 m/s) | 180 | 5.0 | 10.3 | 463.4 |

One real teleport (463 m: the sim's start sits near waypoint 4, then jumps to the
route's start). The other 179 are `nmea_sim`'s route walker covering 5–12 m per fix.

## The fix

`BREAK_SPEED_MS = 20.0` (72 km/h): no ground rover gets near it, and a teleport is
hundreds of metres. Mission 12 now shows 2 breaks. A test pins that a 10 m/s step is
not a break.

## Prevention

Query the rows before naming a cause. The "two writers" guess was wrong; the data
said so in one query.
