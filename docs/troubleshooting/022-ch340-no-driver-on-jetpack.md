# 022 — CH340 USB-serial adapter enumerates on the Orin but never becomes `/dev/ttyUSB*`

*Date: 2026-09-28*

---

## What we saw

F08 step 1a.1: GPS on a CH340 USB-serial adapter, plugged into the Orin.

```
$ sudo dmesg | tail
[ 3806.026787] usb 1-2.2: new full-speed USB device number 8 using tegra-xusb
$ ls /dev/ttyUSB*
ls: cannot access '/dev/ttyUSB*': No such file or directory
$ ls /dev/serial/by-id/
ls: cannot access '/dev/serial/by-id/': No such file or directory
```

The device arrives on the bus and nothing else happens — no `ch341` line, no
`attached to ttyUSB0`.

## The cause

```
$ lsusb
Bus 001 Device 008: ID 1a86:7523 QinHeng Electronics CH340 serial converter
$ lsusb -t
        |__ Port 2: Dev 8, If 0, Class=Vendor Specific Class, Driver=, 12M
$ find /lib/modules/$(uname -r) -name '*ch34*' -o -name '*cp210*' -o -name '*ftdi*' -o -name 'usbserial*'
/lib/modules/5.15.185-tegra/kernel/drivers/usb/serial/ftdi_sio.ko
/lib/modules/5.15.185-tegra/kernel/drivers/usb/serial/cp210x.ko
/lib/modules/5.15.185-tegra/kernel/drivers/usb/serial/usbserial.ko
```

`Driver=` is empty. The JetPack 6.2.2 kernel (`5.15.185-tegra`) ships no
`ch341.ko`. The same adapter works on the x86 PC, whose stock Ubuntu kernel has
the driver.

## The fix

Moved the GPS to the 40-pin header UART, `/dev/ttyTHS1` (ADR-0014). Identified
the port by MMIO address and proved it with a single jumper from pin 8 to
pin 10:

```bash
$ sudo dmesg | grep -i ttyTHS
3100000.serial: ttyTHS1 at MMIO 0x3100000 ... is a TEGRA_UART    # UARTA → pins 8/10
3140000.serial: ttyTHS2 at MMIO 0x3140000 ... is a TEGRA_UART

$ P=/dev/ttyTHS1
$ stty -F $P 9600 raw -echo -crtscts
$ ( sleep 0.5; echo LOOPBACK_OK > $P ) & timeout 2 cat $P; wait
_OK
```

`_OK` rather than `LOOPBACK_OK`: the first bytes are lost as the port opens.
Irrelevant for a continuous NMEA stream; don't chase it.

Two prerequisites surfaced on the way: `brian` was not in `dialout`
(`sudo usermod -aG dialout $USER`, then re-SSH), and the first loopback attempts
failed only because the "jumper" was the GPS's own TX/RX wires with the module
unpowered — a loopback is one bare wire, nothing else on the header.

## Prevention

- Before choosing a USB-serial adapter for the Orin, check the driver exists:
  `find /lib/modules/$(uname -r) -name '*<chip>*'`. `cp210x` and `ftdi_sio` do;
  `ch341` does not.
- CP2102 is the standing choice for USB-serial on the Orin.
- `lsusb -t` with `Driver=` empty is the one-line diagnosis.
