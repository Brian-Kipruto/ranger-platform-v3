# 023 — GPS silent on the header UART: RX line held low because TX and RX were not crossed

*Date: 2026-09-28*

---

## What we saw

GPS wired to the Orin header, UART proven by loopback (TS-022). Nothing
arrived:

```
$ stty -F /dev/ttyTHS1 9600 raw -echo -crtscts; timeout 5 cat /dev/ttyTHS1
$                                              # nothing
```

Reading raw bytes at several bauds told more than any single read:

```
== 9600
Terminated                                     # zero bytes
== 38400
00000000: 0000 0000 0000 0000 0000 0000 0000 0000  ................
== 115200
00000000: 0000 0000 0000 0000 0000 0000 0000 0000  ................
```

## The cause

A healthy UART line idles **high**. Real NMEA at the wrong baud produces mixed
garbage bytes. A solid run of `0x00` means the line is being **held low** — the
receiver sees one endless start bit.

The GPS's **RX** was on Orin pin 10. Pin 10 is the Orin's *receive* pin, so it
was listening to the GPS's input, which transmits nothing.

The GPS itself was cleared independently by moving it to the CH340 adapter on
the PC (which has the driver), where it streamed clean NMEA immediately:

```
$GNRMC,,V,,,,,,,,,,N*4D
$GNGGA,,,,,,0,00,99.99,,,,,,*56
```

That split the problem in two proven halves — the GPS works, the UART works —
leaving only the four wires between them.

## The fix

Cross the data lines:

| GPS | Orin |
|---|---|
| **TX** | **pin 10** (RXD) |
| **RX** | **pin 8** (TXD) |

After the swap the zeros disappeared (line idle-high), but data still did not
arrive, and the module was then destroyed by a polarity reversal during
rewiring (TS-024). **The crossed header wiring has not yet carried NMEA from a
live module.** It must be re-verified with the replacement before anything
else.

## Prevention

- Read wire labels as *what this pin does*, and cross them: a TX always lands
  on an RX.
- Diagnose with `xxd` at two or three bauds, not `cat` at one: zeros = line held
  low (wiring/power), garbage = wrong baud, nothing at all = idle line
  (unconnected or unpowered), clean `$G…` = done.
- Prove each half on a known-good bench before blaming the joint: UART by
  loopback, device on a machine where it is known to work.

---

## Addendum — 2026-10-03: the header path failed again, with a known-good module

**Status: unresolved. The GPS was moved to FTDI USB (ADR-0014 amendment); the
header is undiagnosed.**

The replacement NEO-6M streamed clean NMEA on the PC through the FTDI cable, with
a fix, the same morning. On the header — VCC→2, GND→6, TX→10, RX→8, pin 4
confirmed empty by touch — it produced nothing usable. Each step below moved one
variable:

| Test | Result | Reading |
|---|---|---|
| GPS on header, `xxd` on `ttyTHS1` at 9600/38400 | solid `0x00`; a later run nothing; then `0x00` again | line flipping between held-low and idle |
| `sudo fuser -v /dev/ttyTHS1` | nothing | no other process on the port |
| GPS on **header power**, GPS TX → FTDI RX on the PC | nothing | **the GPS does not run on header power** |
| GPS on **cable power**, GPS TX → FTDI RX on the PC | clean NMEA | the module is alive |
| GPS on **cable power**, GPS TX → Orin "pin 10" | nothing on `ttyTHS1` | **"pin 10" hears nothing** even from a powered, transmitting GPS |

Two independent failures — no power from "pins 2/6", no data into "pin 10" —
from four wires that look right. And the line alternating between held-low and
idle with no code change is what a **floating** input does, not what any fixed
wiring fault does.

**Lead theory (unproven): the wires are on the wrong row.** On Pi-style 40-pin
headers the even pins (2, 4 … 40) run along the board's outer edge and the odd
pins along the inner row. The wires sit on the inner row. If that row is odd,
the "2, 6, 8, 10" positions are really 1, 5, 7, 9:

| Intended | Actually (if odd row) | Effect |
|---|---|---|
| VCC → 2 (5 V) | 1 (3.3 V) | |
| GND → 6 | 5 (I²C SCL) | **no ground** — GPS unpowered |
| RX → 8 | 7 (GPIO) | |
| TX → 10 | 9 (GND) | GPS TX into ground; pin 10 untouched and floating |

That accounts for every row of the table above. Against it: the 2026-09-28
loopback passed — but nothing recorded whether that jumper sat in the same row
as these wires.

**The settling test (not yet run):** power off, remove the GPS, put one jumper
between the exact two positions the GPS's TX and RX wires occupied, power on,
loopback. Echo back → those are 8/10 and the theory is wrong. Nothing → repeat on
the edge row; whichever pair loops back is 8/10, and 2/6 are in that row.

## Prevention (revised)

- Identify the even row from the board itself — the pin-1 marker and which row
  runs along the board edge — and photograph it **straight down, both rows and
  the marker in frame**, before wiring. Two angled photos could not settle it.
- Prove the exact wire positions with a loopback, not the pins you believe you
  used.
- A receive line that alternates between `0x00` and silence with no changes is
  probably connected to nothing.
