# ─── RANGER V3 START: 08-gps-ingest ───
"""Writes synthetic NMEA GGA at 1 Hz to a (pty) device. Test tool — no GPS needed.

    python3 nmea_sim.py [PATH] [--site {nairobi,rabat}]    # default: /tmp/gps_feed, nairobi
    python3 nmea_sim.py /tmp/gps_feed --site nairobi --route route.geojson [--speed 2.0]
        [--offset-east-m 0] [--jitter-m 0.5] [--lead-in-m 15]     # F15: walk a mission route
"""
import argparse
# ─── RANGER V3 START: 15-sim-route ───
import json
import math
import sys
# ─── RANGER V3 END: 15-sim-route ───
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


# ─── RANGER V3 START: 15-sim-route ───
# Route mode (F15 fork 6). The route is a GeoJSON LineString written by the
# PC's `manage.py mission_route` — [lon, lat] by the GeoJSON spec, so there is
# no typed coordinate to swap. Positions are walked in a local metric frame
# (equirectangular about the first waypoint; exact enough over a few km).
M_PER_DEG = 111_320.0
MAX_ROUTE_KM_FROM_SITE = 5.0
MAX_SPEED_MS = 20.0


def load_route(path):
    """GeoJSON Feature/FeatureCollection with a LineString (or a Point, for a
    one-waypoint mission) -> [(lat, lon), ...] in order."""
    with open(path) as f:
        gj = json.load(f)
    if gj.get('type') == 'FeatureCollection':
        feats = gj.get('features') or []
        if not feats:
            raise ValueError('route has no features')
        gj = feats[0]
    geom = gj.get('geometry', gj) if gj.get('type') == 'Feature' else gj
    kind, coords = geom.get('type'), geom.get('coordinates')
    if kind == 'Point':
        coords = [coords]
    elif kind != 'LineString':
        raise ValueError(f'route geometry must be LineString or Point, got {kind!r}')
    if not coords:
        raise ValueError('route has no coordinates')
    return [(float(c[1]), float(c[0])) for c in coords]  # GeoJSON is [lon, lat]


def km_between(a, b):
    """Haversine, km."""
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def check_route_near_site(route, site):
    """The route must start near --site. Also catches a swapped route, which
    lands hundreds of km away."""
    d = km_between(route[0], site[:2])
    if d > MAX_ROUTE_KM_FROM_SITE:
        raise ValueError(f'route starts {d:.1f} km from the site (max {MAX_ROUTE_KM_FROM_SITE} km) '
                         '— wrong --site, or a swapped lat/lon?')
    return d


def walk(route, speed_ms, lead_in_m=15.0, offset_east_m=0.0):
    """Yield (lat, lon, wp_index_or_None), one per second, forever.

    Starts lead_in_m before waypoint 1 (back along the first leg), walks each
    leg in steps of at most speed_ms metres, and ALWAYS yields each waypoint
    itself — a fast walk can never step over a threshold circle. After the
    last waypoint it holds there. offset_east_m shifts everything east (the
    miss proof). wp_index marks the fix that sits exactly on a waypoint.
    """
    lat0, lon0 = route[0]
    kx = M_PER_DEG * math.cos(math.radians(lat0))

    def to_xy(p):
        return ((p[1] - lon0) * kx, (p[0] - lat0) * M_PER_DEG)

    def to_ll(x, y):
        return (lat0 + y / M_PER_DEG, lon0 + (x + offset_east_m) / kx)

    pts = [to_xy(p) for p in route]
    if len(pts) > 1 and math.dist(pts[0], pts[1]) > 0:
        ux, uy = [(b - a) / math.dist(pts[0], pts[1]) for a, b in zip(pts[0], pts[1])]
    else:
        ux, uy = 0.0, 1.0  # one waypoint: approach from the south
    cur = (pts[0][0] - ux * lead_in_m, pts[0][1] - uy * lead_in_m)
    yield (*to_ll(*cur), None)
    for i, target in enumerate(pts):
        n = max(1, math.ceil(math.dist(cur, target) / speed_ms))
        for k in range(1, n + 1):
            x = cur[0] + (target[0] - cur[0]) * k / n
            y = cur[1] + (target[1] - cur[1]) * k / n
            yield (*to_ll(x, y), i if k == n else None)
        cur = target
    while True:
        yield (*to_ll(*cur), None)


def closest_approach(route, speed_ms, lead_in_m=15.0, offset_east_m=0.0):
    """Metres from each waypoint to the nearest fix of the (jitter-free) walk.
    Printed before a run so the operator knows the expected outcome. With an
    offset, what matters is waypoint 1: the platform never skips ahead, so if
    1 is missed nothing completes — unless a later leg passes back near it."""
    best = [math.inf] * len(route)
    last = len(route) - 1
    for lat, lon, wp in walk(route, speed_ms, lead_in_m, offset_east_m):
        for i, w in enumerate(route):
            best[i] = min(best[i], km_between((lat, lon), w) * 1000)
        if wp == last:
            break
    return best


def jittered(lat, lon, jitter_m):
    if jitter_m <= 0:
        return lat, lon
    return (lat + random.uniform(-jitter_m, jitter_m) / M_PER_DEG,
            lon + random.uniform(-jitter_m, jitter_m) / (M_PER_DEG * math.cos(math.radians(lat))))


def run_route(f, args, site):
    route = load_route(args.route)
    d = check_route_near_site(route, site)
    legs = sum(km_between(a, b) for a, b in zip(route, route[1:])) * 1000 + args.lead_in_m
    print(f'nmea_sim: route {args.route}: {len(route)} waypoints, {legs:.0f} m, '
          f'~{legs / args.speed:.0f} s at {args.speed} m/s, offset_east={args.offset_east_m} m, '
          f'jitter={args.jitter_m} m, start {d:.2f} km from {args.site}', flush=True)
    near = closest_approach(route, args.speed, args.lead_in_m, args.offset_east_m)
    print('nmea_sim: closest approach (m, before jitter): '
          + ' '.join(f'wp{i + 1}={m:.1f}' for i, m in enumerate(near)), flush=True)
    for _ in range(3):  # same no-fix warm-up as site mode
        f.write(gga(False).encode())
        time.sleep(1)
    held = False
    for lat, lon, wp in walk(route, args.speed, args.lead_in_m, args.offset_east_m):
        jl, jo = jittered(lat, lon, args.jitter_m)
        f.write(gga(True, site=(jl, jo, site[2]), jitter_min=0).encode())
        if wp is not None:
            print(f'nmea_sim: at waypoint {wp + 1}/{len(route)} {lat:+.6f},{lon:+.6f}', flush=True)
            if wp == len(route) - 1 and not held:
                held = True
                print('nmea_sim: route done, holding at the last waypoint', flush=True)
        time.sleep(1)
# ─── RANGER V3 END: 15-sim-route ───


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('path', nargs='?', default='/tmp/gps_feed')
    ap.add_argument('--site', choices=sorted(SITES), default='nairobi')  # F11
    # ─── RANGER V3 START: 15-sim-route ───
    ap.add_argument('--route', help='GeoJSON from `manage.py mission_route`; walk it instead of standing still')
    ap.add_argument('--speed', type=float, default=2.0, help='route mode: m/s (default 2.0)')
    ap.add_argument('--offset-east-m', type=float, default=0.0, help='route mode: shift the walk east (miss proof)')
    ap.add_argument('--jitter-m', type=float, default=0.5, help='route mode: +/- metres per axis (default 0.5)')
    ap.add_argument('--lead-in-m', type=float, default=15.0, help='route mode: start this far before waypoint 1')
    # ─── RANGER V3 END: 15-sim-route ───
    args = ap.parse_args()
    site = SITES[args.site]
    # ─── RANGER V3 START: 15-sim-route ───
    if args.route:
        if not 0 < args.speed <= MAX_SPEED_MS:
            ap.error(f'--speed must be in (0, {MAX_SPEED_MS}] m/s')
        if args.jitter_m < 0 or args.lead_in_m < 0:
            ap.error('--jitter-m and --lead-in-m must be >= 0')
        try:
            check_route_near_site(load_route(args.route), site)  # fail before opening the pty
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            sys.exit(f'nmea_sim: bad route: {exc}')
        with open(args.path, 'wb', buffering=0) as f:
            run_route(f, args, site)
        return
    # ─── RANGER V3 END: 15-sim-route ───
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
