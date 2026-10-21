# ADR-0023: Teleop goes browser → Channels → relay → rosbridge, with four stop layers

- **Status:** Accepted (proven on wheels over the tether and over Wi-Fi)
- **Date:** 2026-10-19 (Wi-Fi results 2026-10-20)
- **Feature:** F14 (Drive and Video), checkpoint 5a
- **Related:** ADR-0016 (WebSocket token auth), ADR-0022 (arbitration in the Uno), ADR-0026 (firewall)

## Context

rosbridge has no authentication: anyone who can reach `:9090` can publish
`/ranger/cmd_vel`. The console already has authenticated WebSockets (ADR-0016) and a
Redis channel layer. A robot that is driven must also stop on its own when any link
in the chain fails.

## Decision 1 — The browser never talks to rosbridge

```
browser DRIVE panel ─/ws/teleop/<robot>/─▶ TeleopConsumer ─Redis teleop.robot.<pk>─▶ teleop_relay (PC)
   ─rosbridge─▶ /ranger/cmd_vel ─▶ uno_bridge (Orin) ─M,<l>,<r>─▶ Uno
```

- **Auth:** ADR-0016 token; permission `core.drive_robot`, granted through the
  **Drivers** group (`manage.py grant_drive <user>`); robot looked up within the
  user's organization.
- **Close codes** (all after accept, so the browser sees them): 4401 bad token, 4403
  no organization, 4404 unknown or other org's robot, 4405 no `core.drive_robot`,
  4409 someone else is driving / lease lost.
- **One driver per robot:** a Redis lease, `SET NX PX 3000`, refreshed by its owner
  on every message, released by its owner only. A crashed worker can't hold a robot
  longer than 3 s.

## Decision 2 — `cmd_vel` is normalised, not SI

`linear.x` and `angular.z` in [−1, 1] of `max_pwm`, REP-103 signs; `uno_bridge`
mixes them differentially and scales (not clips) when a side exceeds 1. No
wheel-speed calibration exists yet, so SI units would be a lie.

## Decision 3 — Four independent stop layers, under the RC layer

| Layer | Stops when | Measured |
|---|---|---|
| Browser | key/pointer released, Space, window blur, hidden tab, unmount (hold-to-drive) | every trigger |
| `teleop_relay` | a command is > 300 ms old (drops it); sends a zero on exit | 51 queued commands dropped |
| `uno_bridge` | `cmd_vel` > 250 ms stale → one `M,0,0` | 252–298 ms (tether), 258–294 ms (Wi-Fi) |
| Uno | no `M` for 250 ms | `m_age=251` |

Under all four: RC link lost (100 ms) and SwA in RC both stop network driving
(ADR-0022). Each layer works with every layer above it dead.

## Consequences

- Wi-Fi jitter is safe as long as it stays under 250 ms: a 10 s continuous hold
  over Wi-Fi produced no extra stops; a relay `kill -9` mid-drive stopped the robot
  314 ms later.
- rosbridge stays reachable from the PC, so the firewall (ADR-0026), not rosbridge,
  keeps strangers off `cmd_vel`; the RC consent switch remains the last guard.
- Drive tests published straight to `cmd_vel` on the Orin (the magnetometer test)
  bypass the console by design; every physical stop layer still applies.
