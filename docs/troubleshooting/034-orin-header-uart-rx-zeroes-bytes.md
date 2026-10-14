# 034 — The Orin's header UART receives the first 8 bytes of every burst as `0x00`

*Date: 2026-10-13*

---

## What we saw

F13 planned to run the SDS011 from the Orin's 40-pin header UART (pins 8/10,
`/dev/ttyTHS1`), since there was no second USB-UART adapter. Loopback, pin 8 ↔
pin 10, 9600 baud:

```
b'\x00\x00\x00\x00\x00\x00\x00\x00OOP\n' 17 ms          # sent b'RANGER-LOOP\n'
BAD 0 b'\x00\x00\x00\x00\x00\x00\x00\x0000\n'           # sent b'RANGER-000\n'
…
0/50 exact, worst 16 ms
```

Every write came back with exactly its first 8 bytes zeroed and the rest
intact. Deterministic, not noise.

## Isolating TX from RX

A loopback can't say which side is broken. The GPS's FTDI cable, plugged into
the Orin, listened to pin 8 only (FTDI RX → pin 8, GND → pin 6; nothing into
pin 10, so a 5 V FTDI could do no harm):

```
TX test: 20/20 exact
```

**The Orin transmits correctly; its receiver zeroes the first 8 bytes after
idle.** The cause is in the Tegra UART's receive path (likely its DMA or FIFO
handling); not investigated further.

The same run confirmed the header rows by function: GND on pin 6 worked.

## Why it rules out the SDS011

The SDS011 sends a 10-byte frame once a second, with idle between frames. Each
frame would lose 8 of its 10 bytes.

## The fix

Don't use the header UART for receiving. The SDS011 goes on a **CP2102**
USB-UART (driver `cp210x` is in JetPack's kernel; **not CH340**, which has none —
TS-022). The GPS stays on the FTDI.

Rejected: a device-tree overlay to change the UART's receive mode (JetPack-fragile,
the detour ADR-0014 rejected for CH340); reading the SDS011 through the Uno
(couples PM to F14 firmware; SoftwareSerial blocks the Geiger interrupt).

## Prevention

- Prove a serial path in **both** directions separately before planning on it.
- Likely explains TS-023's "solid `0x00`" from the NEO-6M on this header in F08
  — NMEA also arrives in bursts. Unconfirmed.
