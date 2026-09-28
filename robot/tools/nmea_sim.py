# ─── RANGER V3 START: 08-gps-ingest ───
"""Writes synthetic NMEA GGA at 1 Hz to a (pty) device. Test tool — no GPS needed."""
import random
import sys
import time
from datetime import datetime, timezone


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f'{c:02X}'


def gga(has_fix):
    t = datetime.now(timezone.utc).strftime('%H%M%S.00')
    if has_fix:
        lat_min = 17.1840 + random.uniform(-0.002, 0.002)   # -1.2864 deg
        lon_min = 49.0320 + random.uniform(-0.002, 0.002)   # 36.8172 deg
        body = f'GNGGA,{t},01{lat_min:07.4f},S,036{lon_min:07.4f},E,1,08,1.0,1661.0,M,-13.0,M,,'
    else:
        body = f'GNGGA,{t},,,,,0,00,99.99,,,,,,'
    return f'${body}*{checksum(body)}\r\n'


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/gps_feed'
    with open(path, 'wb', buffering=0) as f:
        n = 0
        while True:
            f.write(gga(has_fix=n >= 3).encode())
            n += 1
            time.sleep(1)


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 08-gps-ingest ───
