# 043 — Jittery Wi-Fi between the PC and the Orin: power saving

*Date: 2026-10-20*

---

## What we saw

First pings over the house Wi-Fi: Orin → PC **68 ms average, 122 ms max**; PC → Orin
15 ms average, 59 ms max. The asymmetry pointed at the PC's replies.

## The cause

Ubuntu's `default-wifi-powersave-on.conf` (present on both machines): the Wi-Fi card
sleeps between beacons and delays replies. The Orin's profile already set
`powersave=2`; the PC's "Brian" profile used the default (on).

## The fix

```bash
sudo nmcli connection modify Brian 802-11-wireless.powersave 2 && sudo nmcli connection up Brian
```

After: Orin → PC **8.2 / 40 ms**, PC → Orin **6.8 / 60 ms** (avg / max, 50 pings).
Worst case ~60 ms against the 250–300 ms drive stale limits; a 10 s continuous drive
hold then showed no jitter stops.

## Prevention

- Set `802-11-wireless.powersave 2` on every profile that carries drive traffic,
  PC and Orin, house and venue.
- Measure both directions; an asymmetric RTT points at one end.
