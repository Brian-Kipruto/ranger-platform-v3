# 029 — Orin clock 12 s behind after the TS-025 fallback: `$(date +%s)` expands before the sudo prompt

*Date: 2026-10-06*

---

## What we saw

During F09 2b every saved row's robot stamp trailed wall-clock time by a
steady 12–13 s:

```
# ros_ingest started 10:34:07 EAT (07:34:07Z)
SensorLog #24677: -1.286380, 36.817198 [simulated] @ 07:33:55Z
...
# Ctrl-C at 10:34:33
SensorLog #24702: -1.286423, 36.817228 [simulated] @ 07:34:20Z
```

Constant, so not a backlog. Under the 120 s skew guard (ADR-0015), so nothing
was skipped — but it would have failed F09's < 1 s latency check. `date` on both
machines, typed seconds apart in two terminals, "matched".

## The cause

`gps_node.py` stamps each fix with `self.get_clock().now()` — the Orin's clock.
The Orin had been set with TS-025's fallback, run in a PC terminal:

```bash
ssh -t brian@192.168.55.1 "sudo date -s @$(date +%s)"
```

`$(date +%s)` is expanded **by the PC's shell before ssh starts**. `sudo` then
waits for the password. The Orin was set to a time already ~12 s in the past —
however long the password took to type.

## Measuring it

Two `date` commands in two terminals can't resolve seconds. Bracket one remote
read between two local reads (needs key-based ssh, or the password prompt widens
the bracket):

```bash
ssh-copy-id brian@192.168.55.1          # once
t0=$(date +%s.%N); r=$(ssh brian@192.168.55.1 date +%s.%N); t1=$(date +%s.%N); python3 -c "print(f'orin - pc = {$r-($t0+$t1)/2:+.2f} s  (±{($t1-$t0)/2:.2f})')"
```

```
orin - pc = -9.57 s  (±2.58)     # with a password prompt
orin - pc = -12.01 s  (±0.14)    # after ssh-copy-id
```

## The fix

Time the sudo wait on the Orin's monotonic clock and add it to the PC timestamp
taken at the start (in a PC terminal):

```bash
ssh -t brian@192.168.55.1 "u0=\$(cut -d' ' -f1 /proc/uptime); sudo -v; u1=\$(cut -d' ' -f1 /proc/uptime); sudo date -s @\$(python3 -c \"print($(date +%s.%N)+\$u1-\$u0)\")"
```

```
orin - pc = -0.22 s  (±0.14)
```

The live console then measured `lag=693–710 ms` browser-receipt minus robot
stamp, ~220 ms of which is this residual offset.

After the clock jumped forward three days earlier the same session, `gps_node`
and `nmea_sim` published nothing until restarted (`ros_ingest` reported
`Stopped. {}`). Restart the publishers after any large clock step.

## Prevention

- TS-025's one-liner and the F08 "Running it" block now carry this command.
- Check the offset with the bracketed measurement, not two `date`s.
- NTP did not sync on 2026-10-06 with the NAT up (`ping 1.1.1.1` succeeded);
  name resolution was not checked. Per TS-025, `ping -c 2 google.com` first.
- Field time is still open: no RTC battery, no NTP in the field. GPS UTC is the
  reference (F08 open items).
- **Superseded by F12 (2026-10-07):** the Orin now syncs to chrony on the PC by
  IP; `dev_up.sh` checks instead of setting, and this `sudo date` path runs only
  with `--set-clock` (ADR-0019).
