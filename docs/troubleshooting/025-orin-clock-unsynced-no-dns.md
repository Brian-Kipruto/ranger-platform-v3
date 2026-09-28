# 025 — Orin clock four months behind: NTP active but never synced, because DNS didn't resolve over the USB NAT

*Date: 2026-09-28*

---

## What we saw

The SSH banner said `Last login: Thu May 7 2026` on 2026-09-28.

```
$ timedatectl
               Local time: Thu 2026-05-07 13:54:20 EAT
                 RTC time: Thu 1970-01-01 00:07:36
System clock synchronized: no
              NTP service: active
```

Internet appeared to work — `ping -c 3 8.8.8.8` returned 0% loss after
`bash ~/jetson-internet.sh` on the PC.

Why it matters: `rclpy` stamps every `NavSatFix` from this clock, `apt` rejects
repository metadata "not valid yet", and `ros_ingest` skips fixes more than
120 s from server time (ADR-0015). Unguarded, every row would have been
back-dated to May.

## The cause

```
$ ping -c 2 google.com
ping: google.com: Temporary failure in name resolution
$ timedatectl timesync-status
       Server: n/a (0.fr.pool.ntp.org)
 Packet count: 0
```

Routing worked; name resolution did not. The USB NAT forwards packets but
nothing hands the Orin a DNS server, so `timesyncd` could never resolve a pool
server and sent zero packets. `ping 8.8.8.8` succeeds by IP and hides this.

The RTC reading 1970 means the Orin has no set hardware clock; at boot it
resumes from the last time `timesyncd` saved.

A second, smaller trap: `~/jetson-internet.sh` did not exist on the PC. Its
contents were recorded in the vault's Start Sequences note, but the file had
never been written to disk.

## The fix

```bash
# Orin
sudo sed -i 's/^#\?DNS=.*/DNS=8.8.8.8 1.1.1.1/' /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
sudo systemctl restart systemd-timesyncd
sleep 15; timedatectl | grep -E 'Local|synchronized'
```

```
               Local time: Mon 2026-09-28 14:49:30 EAT
System clock synchronized: yes
```

The first `ping google.com` straight after the restart still failed; it
resolved seconds later. Persistent across reboots (`resolved.conf`).

The NAT script was recreated at `~/jetson-internet.sh` on the PC (interfaces
`wlo1` → `enxe2b7eee57fe4`; check `ip -br link` first — the `enx…` name follows
the MAC).

## Prevention

- Check connectivity by **name**, not IP: `ping -c 2 google.com`.
- Before any ROS session: `timedatectl | grep synchronized` must say `yes`.
- Scripts the start sequence depends on must exist on disk; the vault records
  them, it does not install them.
- **Open:** in the field there is no NAT and no NTP. Set the RTC
  (`sudo hwclock -w` once synced — it only survives power-off with an RTC
  backup battery fitted) and/or discipline the clock from GPS time, or
  `ros_ingest` will reject every fix after an offline reboot.
