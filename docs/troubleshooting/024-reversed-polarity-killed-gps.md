# 024 — NEO-M8N destroyed by reversed supply polarity during rewiring

*Date: 2026-09-28*

---

## What we saw

While re-checking the header wiring (TS-023), VCC and GND were swapped on the
GPS board for a few seconds. Afterwards, back on the known-good bench (CH340 on
the PC, where it had streamed NMEA an hour earlier):

```
$ stty -F /dev/ttyUSB0 9600 raw -echo; timeout 5 cat /dev/ttyUSB0
$                                              # nothing
```

The adapter enumerated normally, but its RX LED — which had blinked with every
NMEA burst before — stayed dark. The module no longer transmits.

## The cause

Reverse polarity across the board's supply. The board (silkscreen
`GY-GPS6MV2`, module `NEO-M8N-0-10`) has no reverse-polarity protection; its
header is labelled `GND TX RX VCC`, with GND and VCC at opposite ends, so a
connector flipped end-for-end reverses the supply exactly.

Wiring was being changed with the Orin powered — hot-plugging VCC was used as a
"does the LED flash" check.

## The fix

None. Replacement NEO-M8N modules ordered (two — a spare before Rabat). F08
continued against a simulated GPS (`robot/tools/nmea_sim.py` over a socat pty)
so nothing downstream was blocked.

## Prevention

- **Power off before touching the header.** `sudo shutdown now`, unplug DC,
  wire, then power on. No hot-plugging to "see if it lights up".
- Count header pins **by touch** from pin 1 (back row, from the pin-1 end:
  2 = 5V, 4 = 5V, 6 = GND, 8 = TXD, 10 = RXD) and check VCC/GND at **both** ends
  of every wire before applying power.
- With a multimeter: GPS VCC→GND ≈ 5 V after power-on, before connecting data.
- Keep a spare of every sensor on the demo path.
