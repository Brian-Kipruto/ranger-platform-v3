# ADR-0027: One-click bench from the dock, not a start button in the console

- **Status:** Accepted
- **Date:** 2026-10-20
- **Feature:** F14 (checkpoint 5e)
- **Related:** ADR-0025 (link-following config), ADR-0026 (firewall)

## Context

Starting the bench took the Orin stack, four PC terminals, a hand-run `uno_bridge`,
camera and video server, and remembering which address each needed. Brian asked for
a start button in the console.

## Decision — `ranger_up.sh` / `ranger_down.sh`, run from dock icons

- `stack_up.sh` starts and checks drive (`uno_bridge`, `/ranger/uno_status`), camera
  and video (one long `/snapshot` proves frames) with the sensors; preflight refuses
  a missing Uno or camera, a broken Orbbec launch file, `0.0.0.0`, hand-started
  copies, and absent firewall rules.
- `ranger_up.sh [dev_up args]` runs `dev_up.sh`, recreates PC tmux session
  `ranger-pc` (runserver, ingest, relay, vite) every time — so Vite rereads its
  config and ingest and relay connect to the stack as it is now — waits for Django
  and Vite, fails if any service exited, opens Mission Control. `dev_up.sh` hands it
  the built commands through a file, so region/live/link logic lives in one place.
- `ranger_down.sh` sends Ctrl-C to every window (clean `M,0,0` and relay zero), then
  removes both sessions; finds the Orin on the tether or Wi-Fi.
- Dock icons (`scripts/desktop/`, `@REPO@` substituted at install) open a terminal
  that stays until Enter.

## Rejected — a start button in the console

- **Chicken-and-egg:** the console needs runserver, Vite and Postgres — the things it
  would start.
- **Remote execution from the web:** a new path to run commands on the robot, on the
  platform F14 spent its effort locking down.
- **Off the critical path** for Rabat when one command does the job.

A **read-only** stack-status panel in the console stays possible later.

## Consequences

8.1 s with the Orin stack up, about 30–60 s cold, 7.4 s down; recovery after a
relay kill is one `ranger_up` (10.3 s).
