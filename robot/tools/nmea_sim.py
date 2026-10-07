# ─── RANGER V3 START: 08-gps-ingest ───
"""Writes synthetic NMEA GGA at 1 Hz to a (pty) device. Test tool — no GPS needed.

    python3 nmea_sim.py [PATH] [--site {nairobi,rabat}]    # default: /tmp/gps_feed, nairobi
"""
import argparse
import random
import time
from datetime import datetime, timezone

# ─── RANGER V3 START: 11-ingest-region ───
# Named sites, never a typed origin: a typed LAT,LON is as invertible as the
# bug the region tripwire exists to catch. (lat, lon, altitude_m), signed degrees.
# rabat MUST equal core.geo.RABAT_VENUE on the PC — test_nmea_hemisphere asserts it.
SITES = {
    'nairobi': (-1.2864, 36.8172, 1661.0),
    'rabat': (34.02, -6.84, 75.0),
}


def _ddmm(deg, width, jitter_min):
    """Signed degrees -> (NMEA ddmm.mmmm / dddmm.mmmm field, abs value).
    Jitter is applied in minutes, exactly as the original Nairobi literals were."""
    a = abs(deg)
    d = int(a)
    m = (a - d) * 60 + random.uniform(-jitter_min, jitter_min)
    return f'{d:0{width}d}{m:07.4f}'
# ─── RANGER V3 END: 11-ingest-region ───


def checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f'{c:02X}'


def gga(has_fix, site=SITES['nairobi'], jitter_min=0.002):
    t = datetime.now(timezone.utc).strftime('%H%M%S.00')
    if has_fix:
        # ─── RANGER V3 START: 11-ingest-region ───
        # Hemisphere letters come from the SIGN — never hard-coded (F11).
        lat, lon, alt = site
        lat_f = _ddmm(lat, 2, jitter_min)
        lon_f = _ddmm(lon, 3, jitter_min)
        ns = 'N' if lat >= 0 else 'S'
        ew = 'E' if lon >= 0 else 'W'
        body = f'GNGGA,{t},{lat_f},{ns},{lon_f},{ew},1,08,1.0,{alt:.1f},M,-13.0,M,,'
        # ─── RANGER V3 END: 11-ingest-region ───
    else:
        body = f'GNGGA,{t},,,,,0,00,99.99,,,,,,'
    return f'${body}*{checksum(body)}\r\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('path', nargs='?', default='/tmp/gps_feed')
    ap.add_argument('--site', choices=sorted(SITES), default='nairobi')  # F11
    args = ap.parse_args()
    site = SITES[args.site]
    print(f'nmea_sim: site={args.site} {site[0]:+.4f},{site[1]:+.4f} -> {args.path}', flush=True)
    with open(args.path, 'wb', buffering=0) as f:
        n = 0
        while True:
            f.write(gga(has_fix=n >= 3, site=site).encode())
            n += 1
            time.sleep(1)


if __name__ == '__main__':
    main()
# ─── RANGER V3 END: 08-gps-ingest ───
