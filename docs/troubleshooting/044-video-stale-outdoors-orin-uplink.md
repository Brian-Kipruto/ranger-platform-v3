# 044 — Video STALE outdoors while drive still works: the Orin's uplink collapses

*Date: 2026-10-21 (low-bandwidth mode 2026-10-24)*

---

## What we saw

Driving untethered, the feed went STALE as soon as the robot left the house; drive
kept working. The Orin's own link log (`iw dev wlP1p1s0 link` every 2 s):

| Where | Signal | Orin `tx bitrate` |
|---|---|---|
| inside | −34 to −42 dBm | 52–144 Mbit/s, two streams (MCS 12–15) |
| outside | −57 to −72 dBm | **6.5–19.5 Mbit/s**, single stream (MCS 0–2) |

## The cause

Video goes Orin → PC, the Orin's **send** direction. HIGH needs ~6 Mbit/s of real
throughput; at a 6.5 Mbit/s link rate with retries it gets far less, frames queue,
and after 2.5 s without one the watchdog says STALE — correctly. Drive commands go
the other way and are tiny. The rate collapse is worse than the signal explains
(−63 dBm normally carries 40+ Mbit/s): losses on the Orin's transmit path — a crowded
2.4 GHz channel and/or the antennas (only one stream outside).

## The fix (part 1, done): send less video

Low-bandwidth profiles with AUTO switching (ADR-0024 addendum). Same walk after: LIVE
~85% of the outdoor minute instead of ~0%; the rest are 0.03–6.1 s gaps where the link
carried nothing.

## The fix (part 2, open): radio

- Check both Wi-Fi antenna leads on the Orin's card are attached, and get the antennas
  out of any metal — upright, on top of the robot. Repeat the walk; look for MCS 2+ and
  two streams outside.
- At the venue (Pass 8): the router near the arena, on a quiet channel.

## How to measure

```bash
# PC: log the Orin's link on the Orin (survives dropouts), walk, then read and stop it
ssh brian@192.168.0.50 'nohup sh -c "while true; do echo \"\$(date -u +%T) \$(iw dev wlP1p1s0 link | grep -E \"signal|tx bitrate\" | tr -s \" \" | tr \"\n\" \" \")\"; sleep 2; done" > /tmp/wifilog.txt 2>&1 &'
ssh brian@192.168.0.50 'cat /tmp/wifilog.txt; pkill -f "iw dev wlP1p1s0 link"'
```

With the console's `[video]` lines (DevTools → Console → ⚙ Preserve log, filter
`[video]`) for STALE / LIVE / PROFILE times.

## Prevention

- Treat drive working and video failing as a bandwidth problem in the Orin → PC
  direction, not a video bug. Read `tx bitrate`, not just `signal`.
- While the feed is STALE, drive only with the robot in direct view and the TX in hand.
