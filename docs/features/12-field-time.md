# F12 — Field Time

*Date: 2026-10-09 (built and proven 2026-10-07)*
*Branch: `feat/field-time` (from `main` @ `7e76b49`)*
*Status: **closed with 4c and 4d on ice.** Over the USB tether the Orin gets its time from the PC with no internet and no hand-set clock; a stalled sync is forced in seconds; nothing starts on a wrong clock. The Wi-Fi leg (4d) and the GPS time witness (4c) are deferred — see Open items. **4d is not optional for the finale.***

---

## What this feature does

ADR-0015 stamps every row with the robot's clock and skips any fix more than
120 s from server time as `clock_skew`. Before F12 the Orin's clock was right
only after `scripts/dev_up.sh` set it by hand with `sudo date` (TS-029): its RTC
reads 1970 after every power-off, and NTP over the PC's NAT needed DNS, which
breaks (TS-025). A reboot away from the PC meant zero rows.

F12 makes **the PC the Orin's time server**:

- **PC:** chrony serves NTP to the tether subnet, and keeps serving its own
  clock when it has no internet (`local stratum 10`).
- **Orin:** systemd-timesyncd takes time from the PC **by IP** only — no pool, no
  DNS.
- **`dev_up.sh` step 3 checks the clock instead of setting it.** If the Orin
  isn't synced it forces one fresh NTP attempt; otherwise it fails loudly. The
  old `sudo date` path survives only behind `--set-clock`.
- **`stack_up.sh` runs the same check-and-force on the Orin** before starting
  anything.
- **`dev_up.sh` takes a link: `[usb|wifi]`** (default `usb`). `wifi` needs the
  Orin's router address, set once in 4d.

The skew guard compares the robot against the PC's clock, so syncing the Orin
to the PC syncs it to exactly the reference it's checked against.

| Checkpoint | Proven with | Status |
|---|---|---|
| 4a — PC time server, Orin syncs over USB | offline-reboot proof; negative proof; sandbox chrony test | ✅ `d1b4a3a` |
| 4b — check not set, forced resync, link argument | stall-recovery, normal and negative proofs on hardware; 12-case stub harness | ✅ `72b09fd` |
| 4c — GPS time witness (`/time_reference`, `orin − gps`) | — | 🧊 on ice |
| 4d — untethered on our travel router | — | 🧊 on ice (needs the router) |

Decision: [ADR-0019](../decisions/0019-pc-time-server-check-not-set.md).
Troubleshooting: [TS-033](../troubleshooting/033-timesyncd-backoff-stalls-resync.md).

---

## Sign-off evidence (2026-10-07; hardware runs: Brian)

### Starting state

- Orin after a power-off with the wall supply connected: `RTC time: Thu
  1970-01-01 00:02:27`, `System clock synchronized: no`.
- Orin timesyncd: `active`, no servers configured (pool fallback, needs DNS).
- PC: Ubuntu 22.04, systemd-timesyncd active, no chrony. Tether address
  `192.168.55.100` (on both USB interfaces the Orin exposes). `ufw` inactive.
- Orin has a Wi-Fi device: `wlP1p1s0` (disconnected).

### 4a — PC time server, Orin syncs over USB

Installing chrony (`4.2-2ubuntu2.1`) removed the PC's systemd-timesyncd, as
expected. Deployed `timesyncd-ranger.conf` (`sha256 13a63439…`) identical on
both machines.

**First sync** corrected the Orin by **+1 d 3 h 53 min 6.1 s**: the clock had
been 28 hours behind since the RTC test, and nothing would have said so until
`clock_skew` skipped every fix.

**Offline reboot (the venue condition).** PC Wi-Fi `disabled`; chrony on its own
clock (`7F7F0101`, stratum 10). Orin shut down, powered on, `dev_up.sh` not run.

| | Result |
|---|---|
| Orin `timesync-status` | `Server: 192.168.55.100`, **stratum 10**, offset **+4.1 ms** |
| Boot to first sync | **56.3 s** (timesyncd started at 24.0 s; one 32 s retry) |
| Fresh boot | restore timestamp `20:39:29`, new timesyncd PID |
| `orin − pc` (ssh bracket) | +0.13 to +0.15 s — measurement bias, see Gotchas |

An earlier online boot gave the same 56.2 s and +2.6 ms.

**Negative.** chrony stopped, Orin rebooted: `synchronized: no`, `Timed out
waiting for reply from 192.168.55.100:123` — it refuses rather than guesses.

**Recovery (found by the negative proof).** After chrony restarted, the Orin
took until **534.9 s** after boot to sync: timesyncd's retry gap roughly doubles
(timeouts at 65.7, 140.2, 278.7 s). See TS-033. Fixed in 4b.

**PC online.** With `local stratum 10` alone, `chronyc tracking` stayed on
`7F7F0101` while sources showed `^*`; upstream root distances were ~1.2 s, over
the default 1 s threshold. Changed to `local stratum 10 distance 3`; three
minutes later the PC tracked `mirror.xcobean.co.ke`, stratum 3. **Not
isolated:** by then sources had settled to ±53–165 ms, which the default would
also accept. Kept as harmless.

**Sandbox (chrony 4.5, upstream unreachable):** `ranger.conf` serves stratum 10,
leap 0; without `local stratum 10` it answers stratum 0, leap 3 (unsynchronised —
clients reject it); a client outside `allow` gets no reply.

### 4b — check not set, forced resync

Deployed `stack_up.sh` (`sha256 a7f96bb8…`) and `sudoers-ranger-timesync`
(`sha256 bf4cd75c…`) identical on both machines. On the Orin: `systemctl` is
`/usr/bin/systemctl` (the path the rule names); `visudo -c` parses all files;
`sudo -n` runs the resync (`rule-ok`) and nothing else (`rc=1`).

| Proof | Result |
|---|---|
| **Stall recovery:** chrony stopped, Orin rebooted, ~3 min into backoff, chrony started, `time scripts/dev_up.sh sim` | step 3 `forcing a fresh NTP attempt` → `orin − pc = +0.11 s · synced to 192.168.55.100`; step 5 `starting fresh (clock was stepped)`; **22.6 s total** (vs ~9 min unaided) |
| **Normal start** | `orin − pc = +0.01 s · synced to 192.168.55.100`, no forcing; `already running (sim:nairobi) — leaving it` |
| **Negative:** chrony stopped | `FAIL: chrony is not running on this PC — the Orin's only time source` at step 3; nothing started |

**Stub harness (sandbox):** real tmux, socat and `nmea_sim`; `timedatectl`,
`sudo`, `systemctl`, `ssh`, `docker` stubbed. `shellcheck` clean.

| Case | Result |
|---|---|
| `stack_up`: synced / unsynced / no sudo rule / PC time server down | starts, no sudo / forces then starts / FAIL, no session / FAIL after wait, no session |
| `dev_up`: synced / chrony down / Orin unsynced / no sudo rule | ok / FAIL step 3 / forced, `clock was stepped` / FAIL step 3 |
| `dev_up`: `wifi` unset / `wifi` with host / `--set-clock` with chrony down | exit 2 with the 4d hint / step 2 skipped, `--host` added / WARN, proceeds |
| `dev_up`: bad link, unknown flag, 4th positional | usage error |

The no-argument default still prints plain `python manage.py ros_ingest`.

---

## Files

| File | Installed as | Role |
|---|---|---|
| `config/pc/chrony-ranger.conf` | PC `/etc/chrony/conf.d/ranger.conf` | `allow 192.168.55.0/24`; `local stratum 10 distance 3` |
| `robot/config/timesyncd-ranger.conf` | Orin `/etc/systemd/timesyncd.conf.d/ranger.conf` | `NTP=192.168.55.100`, empty `FallbackNTP=` |
| `robot/config/sudoers-ranger-timesync` | Orin `/etc/sudoers.d/ranger-timesync` (0440) | `brian` may run exactly `/usr/bin/systemctl restart systemd-timesyncd` without a password |
| `robot/tools/stack_up.sh` | Orin `~/ranger/stack_up.sh` | clock check-and-force before anything starts; `RANGER_TIME_WAIT_S` (default 60) |
| `scripts/dev_up.sh` | — | step 3 check-not-set; `[usb|wifi]`; `--set-clock`; `ORIN_WIFI_HOST`; reused-ssh offset measurement |

## Install (both machines — record of what was done)

**PC (brian@Kipruto):**
```bash
sudo apt install -y chrony                      # removes systemd-timesyncd
grep -n '^confdir' /etc/chrony/chrony.conf       # confdir /etc/chrony/conf.d
sudo install -m 644 config/pc/chrony-ranger.conf /etc/chrony/conf.d/ranger.conf
sudo systemctl restart chrony
```

**Deploy (PC):**
```bash
scp robot/config/timesyncd-ranger.conf robot/config/sudoers-ranger-timesync robot/tools/stack_up.sh brian@192.168.55.1:~/ranger/
# compare sha256sum on both machines
```

**Orin (brian@jetson-orin):**
```bash
sudo install -D -m 644 ~/ranger/timesyncd-ranger.conf /etc/systemd/timesyncd.conf.d/ranger.conf
sudo systemctl restart systemd-timesyncd
sudo visudo -cf ~/ranger/sudoers-ranger-timesync \
 && sudo install -m 0440 -o root -g root ~/ranger/sudoers-ranger-timesync /etc/sudoers.d/ranger-timesync \
 && sudo visudo -c
```

## Running it

Unchanged: `scripts/dev_up.sh [sim|live] [nairobi|rabat]`. New:
`… [usb|wifi]` (4d) and `--set-clock` (fallback only).

Check the Orin's time source by hand:
```bash
ssh brian@192.168.55.1 'timedatectl timesync-status | grep -E "Server|Stratum|Offset"'
chronyc tracking | grep -E "Reference ID|Stratum"      # PC
```

## Gotchas

**chrony must stay running on the PC.** It is the Orin's only time source.
`dev_up.sh` step 3 fails without it.

**`synchronized: yes` doesn't say which server.** Check `Server:` is the PC.

**Stratum 10 is the PC serving its own clock** (no internet). Stratum 3 means
the PC itself is on internet time.

**The ssh-bracket offset read +0.13–0.15 s** while timesyncd reported a few ms:
the Orin's `date` runs at the end of the ssh handshake, past the bracket's
midpoint. `dev_up.sh` now warms a reused ssh connection first; the bias dropped
to +0.01 s.

**`sudo` over plain `ssh` can't prompt.** Use `ssh -t` for anything that needs
the Orin's password; only the timesyncd restart is password-free.

**Never give the time path a hostname.** The Orin's DNS breaks (TS-025).

**Boot to first sync is ~56 s over USB,** because timesyncd starts before the USB
link and waits one 32 s retry. `stack_up.sh` allows 60 s; `dev_up.sh` forces a
resync first.

## Open items

- **🧊 4d — untethered on the travel router. Required for the finale:** the robot
  can't drive on a tether, and Pass 5 teleop/video and Pass 8's dry run assume it.
  Needs: the router; DHCP reservations for the PC and the Orin; the Orin
  auto-joining at boot; then `ORIN_WIFI_HOST` in `dev_up.sh`, the router subnet in
  `chrony-ranger.conf` `allow`, the PC's router address in `timesyncd-ranger.conf`
  `NTP=`; then the whole stack over Wi-Fi (measure `lag=`), and the rehearsal: USB
  unplugged, Orin on the rover battery, PC offline, reboot, `dev_up.sh live <site>
  wifi`, rows land with `clock_skew: 0`. Spec: vault *Pass 4*, checkpoint 4d.
- **🧊 4c — GPS time witness.** `gps_node` parses RMC (time + date), publishes
  `sensor_msgs/msg/TimeReference` on `/time_reference`; `dev_up.sh live` prints
  `orin − gps`. The only check on the PC's own clock drifting offline at the
  venue. Needs the NEO-6M under open sky. Spec: vault *Pass 4*, checkpoint 4c.
- **RTC coin cell** — optional; covers boot-to-link-up. Re-run the shutdown test
  after fitting.
- **The `distance 3` cause is unconfirmed** (see 4a).
