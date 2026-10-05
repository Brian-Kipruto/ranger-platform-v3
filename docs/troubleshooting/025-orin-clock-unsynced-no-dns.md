# 025 — Orin clock wrong: no DNS over the USB NAT, because `/etc/resolv.conf` points into `/run` and nothing regenerates it

*Date: 2026-09-28 · Rewritten 2026-10-03 — the first two fixes were wrong*

---

## What we saw

**2026-09-28.** The SSH banner said `Last login: Thu May 7 2026`.

```
$ timedatectl
               Local time: Thu 2026-05-07 13:54:20 EAT
                 RTC time: Thu 1970-01-01 00:07:36
System clock synchronized: no
              NTP service: active
```

**2026-10-03, after a reboot.** Sep 28 instead of Oct 3. Later the same day,
after a clock that had been set by hand: **22 minutes slow**, caught only by
comparing against the GPS's own UTC (`$GPGGA,140123.00,…` while the Orin read
13:39).

Every time, `ping -c 2 8.8.8.8` succeeded and `ping -c 2 google.com` failed:

```
ping: google.com: Temporary failure in name resolution
```

Why it matters: `rclpy` stamps every `NavSatFix` from this clock, `apt` rejects
repository metadata "not valid yet", and `ros_ingest` skips fixes more than
120 s from server time (ADR-0015). Unguarded, every row would be back-dated.

## The cause

Routing works; name resolution doesn't. `timesyncd` can't resolve a pool
server, so it sends zero NTP packets (`Packet count: 0`).

```
$ ls -l /etc/resolv.conf
/etc/resolv.conf -> ../run/resolvconf/resolv.conf
$ cat /etc/resolv.conf
$                                   # empty
```

`/etc/resolv.conf` is a symlink into `/run`, which is tmpfs — wiped every boot —
and nothing on this image regenerates the file at startup. glibc reads an empty
file and has no nameserver.

The Orin has no running RTC (`RTC time: 1970`), so with no NTP the clock resumes
from whatever was last saved and drifts from there.

## Fixes that did not work

1. **`DNS=8.8.8.8 1.1.1.1` in `/etc/systemd/resolved.conf`** (2026-09-28). Seemed
   to work in-session. It can't have been the fix: `/etc/resolv.conf` doesn't
   point at `systemd-resolved`, so nothing reads that line. Gone after reboot.
2. **`/etc/resolvconf/resolv.conf.d/head` + `sudo resolvconf -u`** (2026-10-03).
   Worked until the next reboot — `head` is only applied when `resolvconf`
   regenerates the file, and at boot nothing does. `head` still held the
   nameservers while `/etc/resolv.conf` was empty again.

## The fix

Replace the symlink with a plain file. Nothing regenerates a plain file:

```bash
sudo rm /etc/resolv.conf
printf 'nameserver 8.8.8.8\nnameserver 1.1.1.1\n' | sudo tee /etc/resolv.conf
ping -c 2 google.com
sudo systemctl restart systemd-timesyncd
sleep 15; timedatectl | grep -E 'Local|synchronized'
```

**Not yet verified across a reboot.** Until it is, check `ping google.com` first
thing after every boot.

**Fallback when NTP isn't available** — set the Orin from the PC, accurate to
about a second, which is enough for the skew guard. Run it **in a PC terminal**:

```bash
ssh -t brian@192.168.55.1 "sudo date -s @$(date +%s)"
```

This is how F08 was signed off.

The NAT itself (`~/jetson-internet.sh` on the PC, `wlo1` → `enxe2b7eee57fe4`;
check `ip -br link`) resets on every PC reboot and must be re-run before the
Orin has any internet at all.

## Prevention

- Check connectivity by **name**: `ping -c 2 google.com`. `8.8.8.8` hides this.
- `synchronized: no` does not tell you how wrong the clock is. Compare against a
  reference: `date -u` in a **PC** terminal, or the GPS's GGA time.
  Running `date -u` twice in the Orin's shell compares the Orin with itself —
  done exactly that way on 2026-10-03.
- **In the field there is no NAT and no NTP.** GPS UTC is valid before a
  position fix (`$GPRMC,134641.00,V,…,031026` — time and date, no position) and
  is the natural clock source. Open item: discipline the Orin from GPS time, or
  fit an RTC backup battery and `hwclock -w`.
- Scripts the start sequence depends on must exist on disk; the vault records
  them, it does not install them.
