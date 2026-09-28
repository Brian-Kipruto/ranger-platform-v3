# 026 — `/dev/ttyUSB0` appears and vanishes: brltty claims the CH340

*Date: 2026-09-28*

---

## What we saw

GPS on the CH340 adapter, plugged into the **PC** (Ubuntu, x86_64) to test the
module on a known-good host (TS-023):

```
$ stty -F /dev/ttyUSB0 9600 raw -echo
stty: /dev/ttyUSB0: No such file or directory
```

## The cause

```
$ sudo dmesg | tail -5
input: BRLTTY 6.4 Linux Screen Driver Keyboard as /devices/virtual/input/input30
usb 3-2: usbfs: interface 0 claimed by ch341 while 'brltty' sets config #1
ch341-uart ttyUSB0: ch341-uart converter now disconnected from ttyUSB0
```

`brltty` (a braille-display daemon, installed by default on Ubuntu 22.04)
matches the CH340's USB IDs, grabs the device, and detaches the `ch341` driver.
The port exists for a fraction of a second.

## The fix

```bash
sudo apt remove -y brltty
```

Unplug and replug the adapter:

```
ch341 3-2:1.0: ch341-uart converter detected
usb 3-2: ch341-uart converter now attached to ttyUSB0
```

## Prevention

Remove `brltty` on any Ubuntu 22.04 machine that will talk to USB-serial
hardware. It applies to the Orin too (also 22.04) the moment a CH340 gets a
driver there. `dmesg | tail` right after plugging in names it immediately.
