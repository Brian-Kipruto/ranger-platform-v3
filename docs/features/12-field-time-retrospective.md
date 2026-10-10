# F12 — Retrospective

*Date: 2026-10-09*
*Written at close, with 4c and 4d on ice.*

---

## What worked

**The time server is the reference the guard already uses.** Syncing the Orin to
the PC made the 120 s skew guard agree by construction; no part of the design
depends on the PC having internet.

**Offline was tested as offline.** Two attempts were rejected because the PC was
still online (`ping` answered); the proof only counted once Wi-Fi was off and
chrony showed stratum 10 *after* a two-minute wait, not just after a restart.

**The negative proof found the real bug.** "It refuses without a server" passed;
timing the recovery exposed timesyncd's doubling backoff — minutes of
`clock_skew` in the field. Fixed and re-measured: ~9 min → 22.6 s.

**Check, don't fix.** `dev_up.sh` used to paper over a wrong clock with `sudo
date`. Now a broken time server fails at step 3 with its cause, and the old path
is an explicit flag.

**Shell scripts were run before they were handed over** — a 12-case stub harness
covered both scripts' failure paths before any hardware run.

**A measurement artefact was found and removed.** The steady +0.13–0.15 s
`orin − pc` was the ssh handshake, not the clock; a reused connection brought it
to +0.01 s.

## What went wrong

**Files not handed over, twice.** Both 4a and 4b were built and staged, and the
handoff message went out without the files attached. Caught by Brian both times.

**Commands on the wrong machine, three times.** An offset measurement and a
`dev_up.sh` run went to the Orin's terminal; one Orin check was pasted unrun.
Harmless each time, and each cost a round trip. The prompt is the check.

**A commit landed on `main`.** The branch-creation step was skipped, and 4a was
committed to local `main`. Nothing was pushed; recovered with `git branch` +
`git branch -f main origin/main` before anything left the machine.

**`sudo` over plain `ssh`.** The stall proof's `ssh … 'sudo reboot'` couldn't
prompt for a password. Needed `ssh -t`.

**A change whose effect wasn't isolated.** `distance 3` went in to fix the PC
tracking its own clock while online; by the time it was checked, the sources had
also settled. Recorded as unconfirmed rather than claimed.

**Scope met reality.** The pass promised an untethered robot. The router isn't
bought and the GPS wasn't outdoors, so the pass closes with the USB leg proven
and 4c/4d deferred — explicitly, not quietly.

## Carry-forwards

- **4d before Pass 8, and before driving on the ground in Pass 5.** Buy the
  router; reservations; Orin auto-join; then the rehearsal. Spec in the vault.
- **4c when the NEO-6M is outdoors.** Spec in the vault.
- RTC coin cell (optional).
- chrony is infrastructure on the PC: keep it running.
- Still open from F11: AEOC venue coordinates; first live N/W fix in Morocco;
  per-robot ingest lock (TS-032).
