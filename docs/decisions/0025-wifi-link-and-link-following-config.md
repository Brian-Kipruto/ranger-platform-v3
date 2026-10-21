# ADR-0025: Wi-Fi link — fixed addresses, time over Wi-Fi, one argument moves everything

- **Status:** Accepted (house network; the venue network is Pass 8)
- **Date:** 2026-10-20
- **Feature:** F14 (checkpoint 4d of Pass 4, done on `feat/drive-video`)
- **Related:** ADR-0019 (PC time server, check not set), ADR-0026 (firewall), TS-037, TS-043
- **Changes:** F12's 4d plan said "DHCP reservations for both"; the Orin uses a static address instead

## Context

The robot can't drive on a USB tether. The Orin has an onboard Wi-Fi card that had
never been used. The PC is the Orin's only time source and, with the firewall, its
only allowed peer — so both ends need addresses that don't move.

## Decision 1 — Orin static, PC reserved

- **Orin:** `192.168.0.50`, outside the router's DHCP pool (.100–.200), in a
  NetworkManager profile (`ranger-house`): autoconnect at boot, power saving off,
  gateway and DNS from the router. Router-independent: it works whatever the router
  can do.
- **PC:** a reservation for `192.168.0.102` on the router, so its everyday Wi-Fi
  is unchanged. Power saving off on its profile (TS-043).
- **AP isolation off** on the router, or Wi-Fi clients can't reach each other.

## Decision 2 — Time over Wi-Fi first, the tether second

timesyncd `NTP=192.168.0.102 192.168.55.100` (it moves on when a server doesn't
answer); chrony on the PC `allow 192.168.0.50` — the Orin only, not the subnet.
Proven untethered: `synced to 192.168.0.102`, orin − pc within 0.01 s.

## Decision 3 — One link argument drives every address

`dev_up.sh … [usb|wifi]` (and `ranger_up.sh`, which passes it on) sets the Orin host,
and from it: ingest and relay `--host`, `web_video_server --video-bind`, the console's
video URL (passed to Vite as environment variables, which win over `.env`), and the
stack's mode marker `…+video@<bind>`, so switching link rebinds the feed instead of
"already running — leaving it".

## Consequences

- Untethered cold start: 49 s (`dev_up`), 58 s (`ranger_up`); reboot to Wi-Fi ssh
  109–112 s.
- The venue network needs its own addresses in four places (firewall `ALLOW`,
  chrony `allow`, timesyncd `NTP=`, `ORIN_WIFI_HOST`) and a second NetworkManager
  profile — Pass 8.
