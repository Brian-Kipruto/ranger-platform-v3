# 033 — The Orin stays unsynced for minutes after the PC's time server comes back

*Date: 2026-10-07*

---

## What we saw

F12 4a negative proof: chrony stopped on the PC, Orin rebooted. As intended it
stayed `synchronized: no`. Then chrony was started again — and 90 s later the
Orin was still unsynced.

```
[   23.242601] Started Network Time Synchronization.
[   65.659328] Timed out waiting for reply from 192.168.55.100:123
[  140.158509] Timed out waiting for reply from 192.168.55.100:123
[  278.659019] Timed out waiting for reply from 192.168.55.100:123
[  534.911603] Initial synchronization to time server 192.168.55.100:123
```

## The cause

After each failed attempt systemd-timesyncd waits longer before the next: gaps
of 74, 138, 256 s — roughly doubling. A server that comes back mid-gap isn't
asked until the gap ends. It is not a misconfiguration; nothing was wrong except
the timing.

In the field: if the Orin boots before it can reach the PC (Wi-Fi not up yet,
laptop started after the robot), it can sit unsynced for many minutes, and every
fix is skipped as `clock_skew`.

## The fix

Force a fresh attempt instead of waiting: `systemctl restart
systemd-timesyncd` syncs within seconds once the server answers. `dev_up.sh`
step 3 and `stack_up.sh` do it automatically when the Orin isn't synced (F12 4b,
ADR-0019 Decision 3), via a one-command sudoers rule.

Measured after the fix: chrony stopped, Orin rebooted, ~3 minutes into backoff,
chrony started, `time scripts/dev_up.sh sim` → synced and stack started in
**22.6 s**.

By hand:

```bash
ssh brian@192.168.55.1 'sudo -n /usr/bin/systemctl restart systemd-timesyncd'
```

## Prevention

- Start the stack only through `dev_up.sh` / `stack_up.sh`; both check and force.
- If the Orin reports `synchronized: no`, check `systemctl is-active chrony` on
  the PC first.
- A negative proof that only checks "it refuses" misses recovery. Always time
  the recovery too — that's how this was found.
