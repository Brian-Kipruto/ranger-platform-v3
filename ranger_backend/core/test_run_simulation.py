# ─── RANGER V3 START: 15-sim-advance ───
"""
run_simulation through the one decider (F15 6b.3): the PC-only demo fallback
must advance a mission exactly as a live run does.

Mutation checks (run by hand, each must turn a test red):
  * drop the advance() call in _write_log (mission=None) -> completion tests
  * drop the land-on-target clamp in _move               -> test_long_steps_still_complete_in_order
  * drop self._broadcast(log) in _run_live               -> test_live_broadcasts_every_row
"""
import io
import math

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.geo import RABAT_VENUE, point_from_latlon, resolve_region
from core.management.commands import run_simulation as mod
from core.models import SensorLog
from missions.models import Mission, Waypoint

NAIROBI = (-1.2921, 36.8219)  # run_simulation's default start


def at(base, north_m=0.0, east_m=0.0):
    lat, lon = base
    return lat + north_m / 111_320.0, lon + east_m / (111_320.0 * math.cos(math.radians(lat)))


@pytest.fixture
def make_mission(org, robot):
    def _make(base=NAIROBI, offsets=((0, 0), (50, 0), (50, 50)),
              status=Mission.Status.IN_PROGRESS, region=None):
        bbox = resolve_region(region) if region else resolve_region("kenya")
        m = Mission.objects.create(organization=org, robot=robot, name="sim", status=status)
        for i, (n, e) in enumerate(offsets):
            lat, lon = at(base, n, e)
            Waypoint.objects.create(mission=m, order=i, location=point_from_latlon(lat=lat, lon=lon, region=bbox))
        return m
    return _make


def sim(robot, **kw):
    out = io.StringIO()
    call_command("run_simulation", robot_id_str=robot.robot_id_str, seed=7, stdout=out, stderr=io.StringIO(), **kw)
    return out.getvalue()


def statuses(m):
    return [w.status for w in m.waypoints.order_by("order")]


@pytest.fixture
def stop_after(monkeypatch):
    """Live mode loops forever: stop it after n rows via the sleep it calls."""
    def _arm(n):
        calls = {"n": 0}

        def fake_sleep(_):
            calls["n"] += 1
            if calls["n"] >= n:
                raise KeyboardInterrupt
        monkeypatch.setattr(mod.time, "sleep", fake_sleep)
    return _arm


@pytest.mark.geo
@pytest.mark.django_db
class TestBackfill:

    def test_route_completes_in_order_through_advance(self, robot, make_mission):
        m = make_mission()
        out = sim(robot, count=30, interval_seconds=5, speed=2.0)
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED
        wps = list(m.waypoints.order_by("order"))
        times = [w.completed_at for w in wps]
        assert all(times) and times == sorted(times)
        row_times = set(SensorLog.objects.filter(mission=m).values_list("timestamp", flat=True))
        assert set(times) <= row_times, "completed_at is the completing row's own timestamp"
        assert m.completed_at == times[-1]
        assert "COMPLETED" in out

    def test_rows_are_simulated_and_attached(self, robot, make_mission):
        m = make_mission()
        sim(robot, count=30, interval_seconds=5, speed=2.0)
        attached = SensorLog.objects.filter(mission=m)
        assert attached.exists()
        assert set(SensorLog.objects.values_list("source", flat=True)) == {SensorLog.Source.SIMULATED}

    def test_no_completion_path_outside_advance(self, robot, make_mission, monkeypatch):
        m = make_mission()
        monkeypatch.setattr(mod, "advance", lambda *a, **k: None)
        sim(robot, count=40, interval_seconds=5, speed=2.0)
        assert statuses(m) == ["PENDING"] * 3
        m.refresh_from_db()
        assert m.status == Mission.Status.IN_PROGRESS

    def test_long_steps_still_complete_in_order(self, robot, make_mission):
        """200 m steps against 50 m legs: only the land-on-target clamp gets
        a fix within 5 m of each waypoint."""
        m = make_mission()
        sim(robot, count=10, interval_seconds=10, speed=20.0)
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED

    def test_starts_with_a_lead_in_not_on_the_waypoint(self, robot, make_mission):
        m = make_mission()
        sim(robot, count=1, interval_seconds=5, speed=2.0)
        assert statuses(m) == ["PENDING"] * 3, "first row is 15 m out, outside 5 m"

    def test_pending_mission_is_not_driven(self, robot, make_mission):
        m = make_mission(status=Mission.Status.PENDING)
        sim(robot, count=30, interval_seconds=5, speed=2.0)
        assert statuses(m) == ["PENDING"] * 3
        assert not SensorLog.objects.filter(mission__isnull=False).exists()

    def test_no_mission_random_walks_unattached(self, robot):
        sim(robot, count=5, interval_seconds=5)
        assert SensorLog.objects.count() == 5
        assert not SensorLog.objects.filter(mission__isnull=False).exists()

    def test_speed_must_be_positive(self, robot):
        with pytest.raises(CommandError, match="--speed"):
            sim(robot, count=1, speed=0)


@pytest.mark.geo
@pytest.mark.django_db
class TestRegion:

    def test_rabat_mission_runs_with_region_rabat(self, robot, make_mission):
        m = make_mission(base=RABAT_VENUE, region="rabat")
        sim(robot, count=30, interval_seconds=5, speed=2.0, region="rabat")
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED

    def test_rabat_mission_refused_by_kenya_guard(self, robot, make_mission):
        make_mission(base=RABAT_VENUE, region="rabat")
        with pytest.raises(ValueError, match="outside the expected region"):
            sim(robot, count=5, interval_seconds=5, speed=2.0)

    def test_rabat_random_walk_starts_at_the_venue(self, robot):
        sim(robot, count=1, region="rabat")
        loc = SensorLog.objects.get().location
        assert abs(loc.y - RABAT_VENUE[0]) < 0.01 and abs(loc.x - RABAT_VENUE[1]) < 0.01


@pytest.mark.geo
@pytest.mark.django_db
class TestLive:

    def test_live_completes_and_broadcasts_every_row(self, robot, make_mission, stop_after, monkeypatch):
        sent = []
        monkeypatch.setattr(mod, "broadcast_sensorlog", sent.append)
        m = make_mission()
        stop_after(40)
        sim(robot, live=True, live_delay=1.0, speed=5.0)
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED
        assert [log.pk for log in sent] == list(SensorLog.objects.order_by("pk").values_list("pk", flat=True))

    def test_live_broadcasts_every_row(self, robot, stop_after, monkeypatch):
        sent = []
        monkeypatch.setattr(mod, "broadcast_sensorlog", sent.append)
        stop_after(5)
        sim(robot, live=True, live_delay=1.0)
        assert len(sent) == SensorLog.objects.count() == 5

    def test_broadcast_failure_keeps_rows(self, robot, make_mission, stop_after, monkeypatch):
        def down(log):
            raise ConnectionError("redis down")
        monkeypatch.setattr(mod, "broadcast_sensorlog", down)
        m = make_mission()
        stop_after(40)
        err = io.StringIO()
        call_command("run_simulation", robot_id_str=robot.robot_id_str, live=True, live_delay=1.0,
                     speed=5.0, seed=7, stdout=io.StringIO(), stderr=err)
        assert SensorLog.objects.count() == 40
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED, "a dead socket never blocks progress"
        assert err.getvalue().count("broadcast DOWN") == 1, "logged once, not per row"
# ─── RANGER V3 END: 15-sim-advance ───
