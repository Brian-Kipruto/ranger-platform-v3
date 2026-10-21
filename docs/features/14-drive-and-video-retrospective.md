# F14 — Retrospective

*Date: 2026-10-20*
*Written at close, with current draw carried to Pass 8 and the motor capacitors pending.*

---

## What worked

**Stop layers that don't trust each other.** Browser, relay, bridge and Uno each stop
on their own, under an RC consent switch no software can override. Every layer was
killed in turn on wheels; the robot stopped each time. Over Wi-Fi the numbers stayed
the tether's (stale 258–294 ms, relay kill → stop 314 ms).

**Asking what "frozen" looks like before building the watchdog.** Two probes against
the real server — `/snapshot` hangs with no frames, `/stream` stays 200 with none —
decided the design before a line was written, and the timing was then proven against
the camera's own `ros2 topic hz` log rather than the UI's opinion.

**Measuring the thing, not the proxy.** The RSS test from a fresh 92 MB turned a
suspected leak into a proven +268 MB per 30 s outage and a proven +6 MB fix. The
counters on the firewall chain turned "the firewall doesn't work" into "the test is
masqueraded" in one command.

**Real-world negatives.** The firewall's final proof was a phone on the house Wi-Fi:
refused, open when stopped, frozen when restored. The PC-side test would have
certified nothing.

**Stub harnesses with real parts.** A fake web_video_server, ssh, tmux and lsusb ran
the stack scripts through 17 scenarios; real tmux ran the launcher; real netfilter in
network namespaces ran the firewall. They caught a SIGPIPE false negative (`lsusb |
grep -q` reporting no camera), a missing `.env` aborting `dev_up`, a dead-window check
that never fired, and the link-switch marker bug — all before hardware.

**Building for the operator.** One-click start and stop, a link argument that moves
every address, a `.env` check that names the stale URL, preflight that says which
cable is missing. Brian's "starting them all up is a hassle" became ADR-0027.

**Pushing back on the console button.** A start button in the console would have been
chicken-and-egg and a remote-execution path; the dock launcher gave the same
experience without either.

## What went wrong

**Checks that proved less than they claimed.** `systemctl is-active` passed while
netfilter-persistent had wiped the rules (TS-041); the PC-side intruder test passed
intruders (TS-042); a mutation run without timestamps couldn't be read either way and
had to be redone; an `AFTER` RSS sample was taken before the camera had recovered.
Each was caught, but each cost a round trip. Rule now: a check names the effect it
proves, and every negative test carries timestamps.

**Fixes that created the next bug.** The stream-leak fix reused the `<img>` and broke
under StrictMode (TS-039); the first watchdog fixed frozen frames and queued memory
on the server (TS-040). Both surfaced only on hardware. The harness for the second
design was written after the first failed — it should have come first.

**Commands that didn't run as written.** A wrong repo path on the first command; a
`live` start without the GPS cable that tore down the running sim stack; a patch on
line 46 instead of 47; a grep for `Content-Type` that the server writes as
`Content-type`; an `|| echo` after `head` that could never fire; a `chmod` that didn't
happen in a long chain (caught at commit). Long chained one-liners hide which link
broke; the later blocks print a pass line per step.

**Assumptions about the bench.** That the Orin had a free USB-C port; that the hub was
USB 3; that the stack's existing session would rebind on a link switch; that
`resolv.conf` would stay written. Ask or check before planning around hardware state.

**Speed vs. the session.** 5b alone ran most of a day, with several fixes between
proofs. Splitting at "video works" and "watchdog proven" would have kept each step
smaller.

## Carry-forwards

- Pass 8: current draw; the venue network and its four address entries; battery;
  PC offline; `live` with `clock_skew: 0`.
- Motor capacitors → raise `max_pwm`, rerun the magnetometer test, ground driving.
- `jetson-internet.sh` cleanup; Drivers-group live check; a read-only stack-status
  panel; `wifi` dock launcher; magnetometer calibration (F13).
