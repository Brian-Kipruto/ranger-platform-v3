# ADR-0026: rosbridge and video reachable only from the console PC; the stack checks the rules

- **Status:** Accepted (proven with a separate device as intruder, and across reboots)
- **Date:** 2026-10-20
- **Feature:** F14 (checkpoint 4d)
- **Related:** ADR-0023 (teleop), ADR-0024 (video), TS-041, TS-042

## Context

On Wi-Fi, anyone on the network can reach the Orin. rosbridge (`:9090`) has no auth
— it accepts `cmd_vel` and serves telemetry — and the MJPEG feed (`:8080`) is
unauthenticated by design. The RC consent switch still guards motion, but nothing
guarded the ports.

## Decision 1 — An allowlist chain on the Orin

`ranger-firewall` (iptables, legacy backend on this image):

- chain `RANGER_PORTS`, jumped to from INPUT for TCP 9090 and 8080 only
- allow: loopback, the Orin's own addresses (`addrtype LOCAL`; `stack_up` probes its
  own ports), `192.168.55.100` (PC, tether), `192.168.0.102` (PC, Wi-Fi)
- everyone else: **TCP reset** (fails fast, doesn't hang)
- IPv6: the same chain with no peer allowed (rosbridge also listens on `[::]`)
- ssh is out of scope: key-only, and the way back in

## Decision 2 — Up before the network, after netfilter-persistent

A systemd oneshot, `After=netfilter-persistent.service`, `Before=network-pre.target`.
netfilter-persistent restores `/etc/iptables/rules.v4` with `iptables-restore`, which
replaces the whole filter table; ordered before it, our rules were wiped 9 s after
going in while the unit still said `active` (TS-041).
**Rejected:** writing our rules into `rules.v4` — it mixes ownership of a file another
package manages.

## Decision 3 — The stack checks the rules, not the unit

`ranger-firewall check` exits 0 only if the INPUT jump and the chain's final REJECT
exist, for IPv4 and IPv6. `stack_up.sh` runs it through `sudo -n` (a sudoers line
allows exactly that command) and refuses to start rosbridge and video otherwise.
Whatever wipes the rules in future, nothing starts unprotected.

## Consequences

- Proven with a phone on the house Wi-Fi: both ports refused; firewall stopped →
  the feed loads; restored → an open stream freezes. After reboot: rules in place,
  boot order netfilter-persistent → ranger-firewall → NetworkManager.
- A test **from the PC** can't play intruder: the PC masquerades everything leaving
  `wlo1` (TS-042). Use a separate device.
- The PC's addresses live in `ranger-firewall.sh`; the venue adds its own (Pass 8).
