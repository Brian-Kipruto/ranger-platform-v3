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
