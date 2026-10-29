# ─── RANGER V3 START: 15-sim-route ───
"""
F15 6b.2: nmea_sim --route and manage.py mission_route.

nmea_sim is robot code (stdlib only, deployed flat to the Orin), loaded here by
path like test_nmea_hemisphere. The last class runs 6b in-process: walk ->
GGA -> pynmea2 (gps_node's parse) -> region guard -> missions.progress.advance.

Mutation checks (run by hand, each must turn a test red):
  * walk: drop the forced waypoint fix (step by speed, ignore the vertex)
        -> test_passes_through_every_waypoint_at_speed
  * load_route: read c[0], c[1] as lat, lon (swap)
        -> test_route_round_trips_mission_order_and_coordinates, test_swapped_route_refused
"""
import importlib.util
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pynmea2
import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from core.geo import point_from_latlon
from missions.management.commands.mission_route import route_geojson
from missions.models import Mission, Waypoint
from missions.progress import advance

_SIM = Path(__file__).resolve().parents[2] / "robot" / "tools" / "nmea_sim.py"
_spec = importlib.util.spec_from_file_location("nmea_sim_route", _SIM)
nmea_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nmea_sim)

SITE = nmea_sim.SITES["nairobi"]
LAT0, LON0 = SITE[0], SITE[1]


def at(north_m=0.0, east_m=0.0):
    import math
    return (LAT0 + north_m / 111_320.0,
            LON0 + east_m / (111_320.0 * math.cos(math.radians(LAT0))))


# 3 legs, a corner, ~40 m apart: the shape of a bench mission
ROUTE = [at(20, 0), at(60, 0), at(60, 40), at(20, 40)]


def m_between(a, b):
    return nmea_sim.km_between(a, b) * 1000


def take(gen, n):
    return list(itertools.islice(gen, n))


def write_route(tmp_path, route=ROUTE):
    p = tmp_path / "route.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {},
        "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in route]}}]}))
    return p


class TestWalk:

    @pytest.mark.parametrize("speed", [0.5, 2.0, 3.0, 7.0, 10.0, 20.0])
    def test_passes_through_every_waypoint_at_speed(self, speed):
        fixes = take(nmea_sim.walk(ROUTE, speed, lead_in_m=15), 2000)
        for wp in ROUTE:
            closest = min(m_between((la, lo), wp) for la, lo, _ in fixes)
            assert closest < 0.01, f"at {speed} m/s the walk misses a waypoint by {closest:.2f} m"

    @pytest.mark.parametrize("speed", [0.5, 2.0, 10.0])
    def test_no_step_longer_than_speed(self, speed):
        fixes = take(nmea_sim.walk(ROUTE, speed), 500)
        steps = [m_between(a[:2], b[:2]) for a, b in zip(fixes, fixes[1:])]
        assert max(steps) <= speed * 1.01

    def test_waypoint_flags_mark_the_exact_fix_in_order(self):
        fixes = take(nmea_sim.walk(ROUTE, 2.0), 500)
        flagged = [(f[2], f[:2]) for f in fixes if f[2] is not None]
        assert [i for i, _ in flagged] == [0, 1, 2, 3]
        for i, ll in flagged:
            assert m_between(ll, ROUTE[i]) < 0.01

    def test_lead_in_starts_outside_any_threshold(self):
        first = next(nmea_sim.walk(ROUTE, 2.0, lead_in_m=15))
        assert m_between(first[:2], ROUTE[0]) == pytest.approx(15, abs=0.05)
        assert m_between(first[:2], at(5, 0)) == pytest.approx(0, abs=0.05), "back along leg 1"

    def test_holds_at_the_last_waypoint(self):
        fixes = take(nmea_sim.walk(ROUTE, 2.0), 300)
        assert all(m_between(f[:2], ROUTE[-1]) < 0.01 for f in fixes[-20:])

    def test_offset_misses_waypoint_1_by_the_offset(self):
        """Waypoint 1 is what the miss proof needs: the platform never skips
        ahead. An east shift does NOT miss every waypoint — the shifted
        east-west leg still runs over wp3 — and the report says so."""
        near = nmea_sim.closest_approach(ROUTE, 2.0, offset_east_m=15)
        assert near[0] == pytest.approx(15, abs=0.05)
        assert near[2] < 1.0, "shifted leg 2 runs over wp3 (well inside 5 m)"

    def test_closest_approach_on_route_is_zero(self):
        assert max(nmea_sim.closest_approach(ROUTE, 10.0)) < 0.01

    def test_single_waypoint_route_approaches_from_the_south(self):
        fixes = take(nmea_sim.walk([ROUTE[0]], 2.0, lead_in_m=10), 20)
        assert fixes[0][0] < ROUTE[0][0]
        assert any(f[2] == 0 for f in fixes)

    def test_gga_round_trips_through_gps_node_parse(self):
        for lat, lon, _ in take(nmea_sim.walk(ROUTE, 3.0), 60):
            msg = pynmea2.parse(nmea_sim.gga(True, site=(lat, lon, SITE[2]), jitter_min=0).strip(), check=True)
            assert m_between((msg.latitude, msg.longitude), (lat, lon)) < 0.3  # ddmm.mmmm ~ 0.19 m

    def test_jitter_is_bounded_in_metres(self):
        for _ in range(500):
            jl, jo = nmea_sim.jittered(LAT0, LON0, 0.5)
            assert m_between((jl, jo), (LAT0, LON0)) <= 0.5 * 2 ** 0.5 + 1e-6


class TestLoadRoute:

    def test_reads_lon_lat_in_order(self, tmp_path):
        assert nmea_sim.load_route(write_route(tmp_path)) == pytest.approx(ROUTE)

    def test_point_is_a_one_waypoint_route(self, tmp_path):
        p = tmp_path / "r.geojson"
        p.write_text(json.dumps({"type": "Point", "coordinates": [LON0, LAT0]}))
        assert nmea_sim.load_route(p) == [(LAT0, LON0)]

    def test_rejects_other_geometry(self, tmp_path):
        p = tmp_path / "r.geojson"
        p.write_text(json.dumps({"type": "Polygon", "coordinates": [[[LON0, LAT0]] * 4]}))
        with pytest.raises(ValueError, match="LineString or Point"):
            nmea_sim.load_route(p)

    def test_near_site_accepted(self):
        assert nmea_sim.check_route_near_site(ROUTE, SITE) < 0.1

    def test_swapped_route_refused(self, tmp_path):
        p = tmp_path / "swapped.geojson"
        p.write_text(json.dumps({"type": "LineString", "coordinates": [[lat, lon] for lat, lon in ROUTE]}))
        with pytest.raises(ValueError, match="swapped"):
            nmea_sim.check_route_near_site(nmea_sim.load_route(p), SITE)

    def test_wrong_site_refused(self):
        with pytest.raises(ValueError, match="km from the site"):
            nmea_sim.check_route_near_site(ROUTE, nmea_sim.SITES["rabat"])


class TestCli:

    def _run(self, *argv, tmp_path):
        out = tmp_path / "feed"
        r = subprocess.run([sys.executable, str(_SIM), str(out), *argv],
                           capture_output=True, text=True, timeout=10)
        return r, out

    def test_bad_route_exits_before_opening_the_feed(self, tmp_path):
        p = tmp_path / "swapped.geojson"
        p.write_text(json.dumps({"type": "LineString", "coordinates": [[lat, lon] for lat, lon in ROUTE]}))
        r, out = self._run("--route", str(p), tmp_path=tmp_path)
        assert r.returncode != 0 and "bad route" in r.stderr
        assert not out.exists()

    def test_speed_must_be_positive(self, tmp_path):
        r, _ = self._run("--route", str(write_route(tmp_path)), "--speed", "0", tmp_path=tmp_path)
        assert r.returncode == 2 and "--speed" in r.stderr

    def test_site_mode_unchanged(self, tmp_path):
        """No --route: the stationary sim, as stack_up launches it."""
        out = tmp_path / "feed"
        p = subprocess.Popen([sys.executable, str(_SIM), str(out), "--site", "nairobi"],
                             stdout=subprocess.PIPE, text=True)
        try:
            assert "site=nairobi" in p.stdout.readline()
        finally:
            p.kill()
            p.wait()


@pytest.fixture
def bench_mission(org, robot):
    m = Mission.objects.create(organization=org, robot=robot, name="bench",
                               status=Mission.Status.IN_PROGRESS, threshold_m=5.0)
    for i, (lat, lon) in enumerate(ROUTE):
        Waypoint.objects.create(mission=m, order=i, location=point_from_latlon(lat=lat, lon=lon))
    return m


@pytest.mark.geo
@pytest.mark.django_db
class TestMissionRoute:

    def test_route_round_trips_mission_order_and_coordinates(self, bench_mission, tmp_path):
        out = tmp_path / "route.geojson"
        call_command("mission_route", str(bench_mission.pk), "--out", str(out), stdout=open("/dev/null", "w"))
        gj = json.loads(out.read_text())
        assert gj["features"][0]["geometry"]["type"] == "LineString"
        assert gj["features"][0]["properties"]["threshold_m"] == 5.0
        assert nmea_sim.load_route(out) == pytest.approx(ROUTE, abs=1e-9)

    def test_one_waypoint_is_a_point(self, org, robot):
        m = Mission.objects.create(organization=org, robot=robot, name="one")
        Waypoint.objects.create(mission=m, order=0, location=point_from_latlon(lat=LAT0, lon=LON0))
        assert route_geojson(m)["features"][0]["geometry"] == {"type": "Point", "coordinates": [LON0, LAT0]}

    def test_unknown_mission_errors(self, tmp_path):
        from django.core.management.base import CommandError
        with pytest.raises(CommandError, match="No mission"):
            call_command("mission_route", "999999", "--out", str(tmp_path / "x"))


def run_6b(mission, offset_east_m=0.0, jitter_m=0.5, n=200):
    """Walk the route through the real parse + guard + advance. Returns statuses."""
    for lat, lon, _ in take(nmea_sim.walk(ROUTE, 2.0, offset_east_m=offset_east_m), n):
        jl, jo = nmea_sim.jittered(lat, lon, jitter_m)
        msg = pynmea2.parse(nmea_sim.gga(True, site=(jl, jo, SITE[2]), jitter_min=0).strip(), check=True)
        with transaction.atomic():
            advance(mission.robot, point_from_latlon(lat=msg.latitude, lon=msg.longitude), timezone.now())
    mission.refresh_from_db()
    return mission.status, [w.status for w in mission.waypoints.order_by("order")]


@pytest.mark.geo
@pytest.mark.django_db
class Test6bInProcess:

    def test_route_completes_every_waypoint_then_the_mission(self, bench_mission):
        st, wps = run_6b(bench_mission)
        assert (st, wps) == ("COMPLETED", ["COMPLETED"] * 4)

    def test_15m_offset_leaves_everything_pending(self, bench_mission):
        """wp1 missed by 15 m; wp3 is passed at ~0 m but must NOT complete."""
        st, wps = run_6b(bench_mission, offset_east_m=15)
        assert (st, wps) == ("IN_PROGRESS", ["PENDING"] * 4)

    def test_offset_miss_then_on_route_recovers(self, bench_mission):
        run_6b(bench_mission, offset_east_m=15)
        st, wps = run_6b(bench_mission)
        assert (st, wps) == ("COMPLETED", ["COMPLETED"] * 4)
# ─── RANGER V3 END: 15-sim-route ───
