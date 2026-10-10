# ADR-0019: The PC is the Orin's time server; the clock is checked, not set

- **Status:** Accepted (USB leg proven; Wi-Fi leg pending — F12 4d)
- **Date:** 2026-10-09
- **Feature:** F12 (Field Time)
- **Supersedes:** the clock-setting behaviour of `scripts/dev_up.sh` step 3 (TS-029), now behind `--set-clock`
- **Related:** ADR-0015 (Decision 2: robot stamps, 120 s skew guard), TS-025, TS-029, TS-033

## Context

ADR-0015 records the robot's own timestamp and skips fixes more than 120 s from
server time. That made the Orin's clock load-bearing, and it had no reliable
source: its RTC reads 1970 after every power-off (tested 2026-10-07), and
timesyncd tried pool servers by name over the PC's NAT while the Orin's DNS was
broken (TS-025). The only fix was `dev_up.sh` setting the clock with `sudo date`
over ssh, which needed a password at the keyboard (TS-029) and would not happen
after a reboot in the field. At the finale the PC may have no internet, and the
robot runs on Wi-Fi.

## Decision 1 — The PC serves time; the Orin takes it by IP

PC: chrony, `allow` only the tether (and in 4d the router) subnet,
`local stratum 10 distance 3`. Orin: systemd-timesyncd, `NTP=<PC IP>`, empty
`FallbackNTP=`.

- The skew guard measures the robot against the PC. Syncing the Orin to the PC
  makes them agree by construction, whatever the PC's own accuracy.
- No link to the PC means no rosbridge and no rows anyway, so "PC reachable"
  covers every case where time matters to ingest.
- `local stratum 10` keeps chrony answering with no upstream. Without it chrony
  replies stratum 0 / leap 3 and clients reject it (sandbox-tested) — exactly at
  the venue.
- `distance 3`: the default (1 s) put the PC on its own clock while online, with
  upstream root distances ~1.2 s. Whether this setting or settling time fixed it
  is unconfirmed; it is harmless offline.
- No DNS anywhere in the time path.

| Option | Verdict |
|---|---|
| Discipline the Orin from GPS (gpsd + chrony, PPS) | **Rejected for now** — gpsd would fight `gps_node` for the serial port; the FTDI cable carries no PPS; only matters fully disconnected |
| chrony on the Orin | **Rejected** — timesyncd is already running; one config file |
| RTC coin cell as the fix | **Not sufficient alone** — keeps time across power-off but drifts and can be unset; optional extra |
| Stamp rows with GPS time | **Rejected** — changes what ADR-0015 records |

## Decision 2 — `dev_up.sh` checks the clock; setting it is opt-in

Step 3 fails if chrony isn't running on the PC, and requires the Orin to be
NTP-synced and within 0.5 s. `sudo date` survives only behind `--set-clock`,
with a warning.

Silently patching the clock is how a broken time server would reach Morocco
unnoticed. A failed check names the cause.

## Decision 3 — A stalled sync is forced, not waited out

After failed attempts timesyncd's retry gap roughly doubles; a recovered PC
went unnoticed for ~4 minutes (TS-033). `dev_up.sh` and `stack_up.sh` restart
timesyncd once if the Orin isn't synced, then wait up to 60 s, then fail.
Measured: 22.6 s end to end instead of ~9 minutes.

The restart needs root over ssh without a prompt: one sudoers rule, for exactly
`/usr/bin/systemctl restart systemd-timesyncd`, validated by `visudo -c`.

**Rejected: tuning timesyncd's retry settings** — not confirmed to govern this
gap, and untestable without the Orin; the restart is deterministic.

`stack_up.sh` checks before starting anything: a clock step under running ROS
nodes stalls discovery.

## Decision 4 — The link is an argument; the venue network is ours

`dev_up.sh [sim|live] [nairobi|rabat] [usb|wifi]`. `wifi` uses the Orin's DHCP
reservation on **our own travel router**, set once as `ORIN_WIFI_HOST`.
Venue Wi-Fi commonly isolates clients, which would kill ssh, rosbridge and NTP
at once; our router makes the venue network irrelevant and the setup
rehearsable. Not yet built (4d).

## Consequences

- chrony on the PC is now infrastructure: if it stops, the robot's clock has no
  source and `dev_up.sh` refuses to start.
- Rows are stamped on the PC's timescale. Offline at the venue that is the PC's
  free-running clock; 4c's GPS witness is the planned check on it.
- Three system files are installed outside the repo's runtime (chrony drop-in,
  timesyncd drop-in, sudoers rule). Their sources live in `config/pc/` and
  `robot/config/`; F12 records the install.
