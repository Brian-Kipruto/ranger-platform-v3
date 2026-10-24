# 045 — `no /ranger/uno_status`: the Uno is on USB but sends nothing

*Date: 2026-10-24*

---

## What we saw

After a power cycle, `ranger_up` failed at the drive check: `FAIL: no
/ranger/uno_status within 15 s`. Everything else came up. The Uno was on USB
(`lsusb`: `2341:0043`, the by-id link to `ttyACM0` present), `uno_bridge` opened the
port without error — and logged only its startup line, never `uno mode None -> X`.
A raw read of the port with nothing else attached: `bytes: 0`.

Two false leads on the way: a raw read while the stack's own `uno_bridge` still held
the port (two readers split the bytes), and `pgrep -f "python3 uno_bridge"` matching
its own `ssh` command line (use `pgrep -af "[p]ython3 uno_bridge"`).

## The cause

The USB connection, not the Uno and not the Orin. The Uno on the PC (Arduino IDE
Serial Monitor, 115200): `S,…` every second. Back on the Orin in a **different USB-A
port**, same cable: 193 bytes of `S,…` lines in 5 s, no kernel USB errors. The Uno's
USB chip enumerated on the old port while its main chip stayed silent: a loose or
marginal connection or port. One run can't say which.

## The fix

Reseat the Uno on another USB-A port. Strain-relieve the cable on the robot.

## Prevention

- Uno on `lsusb` but no `/ranger/uno_status`: reseat or move the USB **first**, then
  read raw bytes with the port to yourself:

```bash
ssh brian@192.168.0.50 'pgrep -af "[p]ython3 uno_bridge" || echo NO_BRIDGE; python3 -u -c "
import serial, time
s = serial.Serial(\"/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_3433031323135171F0F0-if00\", 115200, timeout=0.5)
time.sleep(3); t = time.time(); d = b\"\"
while time.time() - t < 5: d += s.read(256)
print(\"bytes:\", len(d)); print(d[:300])"'
```

- The decisive split is the Uno on the PC's Serial Monitor: lines there mean the Uno
  and its firmware are fine.
