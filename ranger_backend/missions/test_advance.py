# ─── RANGER V3 START: 15-mission-advance ───
"""
Proximity advance (missions/progress.py), Start, and the ros_ingest hook (F15 6b.1).

Distances are built in METRES from a base point and asserted against PostGIS's
geodesic answer, so a degrees-vs-metres slip fails loudly.

Mutation checks (run by hand, each must turn a test red):
  * `d > mission.threshold_m` -> `False`           -> TestAdvance outside/miss tests
  * drop .order_by("order") / filter(status=PENDING) -> sequence / no-skip tests
  * drop status=IN_PROGRESS in active_mission       -> not-started tests
"""
import math
import threading
import time
from collections import Counter

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.geo import KENYA_BBOX, point_from_latlon
from core.models import Robot, SensorLog
from missions.models import Mission, Waypoint
from missions.progress import advance
from ros_bridge.management.commands import ros_ingest as mod

BASE = (-1.2864, 36.8172)  # nmea_sim's Nairobi site


def at(north_m=0.0, east_m=0.0, base=BASE):
    """(lat, lon) offset from `base` by metres (small-offset approximation)."""
    lat, lon = base
    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def pt(north_m=0.0, east_m=0.0):
    lat, lon = at(north_m, east_m)
    return point_from_latlon(lat=lat, lon=lon)


@pytest.fixture
def make_mission(org, robot):
    """Mission at BASE + offsets (metres). Waypoints 50 m apart northwards by default."""
    def _make(offsets=((0, 0), (50, 0), (100, 0)), status=Mission.Status.IN_PROGRESS,
              threshold_m=5.0, robot=robot, organization=org):
        m = Mission.objects.create(organization=organization, robot=robot, name="t",
                                   status=status, threshold_m=threshold_m)
        for i, (n, e) in enumerate(offsets):
            lat, lon = at(n, e)
            Waypoint.objects.create(mission=m, order=i, location=point_from_latlon(lat=lat, lon=lon))
        return m
    return _make


def offer(robot, north_m=0.0, east_m=0.0, ts=None):
    with transaction.atomic():
        return advance(robot, pt(north_m, east_m), ts or timezone.now())


def statuses(m):
    return [w.status for w in m.waypoints.order_by("order")]


P, C = Waypoint.Status.PENDING, Waypoint.Status.COMPLETED


@pytest.mark.geo
@pytest.mark.django_db
class TestAdvance:

    def test_no_running_mission_returns_none(self, robot):
        assert offer(robot) is None

    @pytest.mark.parametrize("st", ["PENDING", "PAUSED", "COMPLETED", "ABORTED"])
    def test_not_running_is_never_advanced(self, robot, make_mission, st):
        m = make_mission(status=st)
        assert offer(robot) is None
        assert statuses(m) == [P, P, P]

    def test_inside_threshold_completes_at_fix_time(self, robot, make_mission):
        m = make_mission()
        ts = timezone.now() - timezone.timedelta(seconds=3)
        adv = offer(robot, north_m=4.0, ts=ts)
        assert adv.completed and not adv.mission_completed
        assert adv.distance_m == pytest.approx(4.0, abs=0.1), "geodesic metres, not degrees"
        wp = m.waypoints.get(order=0)
        assert (wp.status, wp.completed_at) == (C, ts)
        m.refresh_from_db()
        assert m.status == Mission.Status.IN_PROGRESS and m.completed_at is None

    def test_outside_threshold_leaves_pending(self, robot, make_mission):
        m = make_mission()
        adv = offer(robot, east_m=6.0)
        assert not adv.completed and adv.distance_m == pytest.approx(6.0, abs=0.1)
        assert statuses(m) == [P, P, P]

    def test_miss_then_recover(self, robot, make_mission):
        m = make_mission()
        for d in (12.0, 8.0, 6.0):
            assert not offer(robot, east_m=d).completed
        assert statuses(m) == [P, P, P]
        assert offer(robot, east_m=3.0).completed
        assert statuses(m) == [C, P, P]

    def test_full_route_completes_mission(self, robot, make_mission):
        m = make_mission()
        t = [timezone.now() + timezone.timedelta(seconds=s) for s in (0, 60, 120)]
        for i, north in enumerate((1.0, 51.0, 99.0)):
            adv = offer(robot, north_m=north, ts=t[i])
            assert adv.completed and adv.waypoint.order == i
        assert adv.mission_completed
        m.refresh_from_db()
        assert (m.status, m.completed_at) == (Mission.Status.COMPLETED, t[2])
        assert [w.completed_at for w in m.waypoints.order_by("order")] == t
        assert offer(robot, north_m=99.0) is None, "a completed mission is no longer running"

    def test_never_skips_ahead(self, robot, make_mission):
        m = make_mission()
        assert not offer(robot, north_m=100.0).completed, "at wp3 while wp1 pending"
        assert not offer(robot, north_m=50.0).completed, "at wp2 while wp1 pending"
        assert statuses(m) == [P, P, P]

    def test_one_waypoint_per_fix(self, robot, make_mission):
        m = make_mission(offsets=((0, 0), (1, 0), (2, 0)))  # all within 5 m of each other
        offer(robot, north_m=1.0)
        assert statuses(m) == [C, P, P]
        offer(robot, north_m=1.0)
        assert statuses(m) == [C, C, P]

    def test_threshold_is_per_mission(self, robot, make_mission):
        m = make_mission(threshold_m=10.0)
        assert offer(robot, east_m=8.0).completed
        assert statuses(m) == [C, P, P]

    def test_other_robots_mission_untouched(self, robot, other_robot, other_org, make_mission):
        theirs = make_mission(robot=other_robot, organization=other_org)
        assert offer(robot) is None
        assert statuses(theirs) == [P, P, P]

    def test_running_with_nothing_pending_is_not_auto_completed(self, robot, make_mission):
        m = make_mission(offsets=((0, 0),))
        m.waypoints.update(status=Waypoint.Status.SKIPPED)
        adv = offer(robot)
        assert adv.waypoint is None and not adv.completed
        m.refresh_from_db()
        assert m.status == Mission.Status.IN_PROGRESS

    def test_db_allows_one_running_mission_per_robot(self, make_mission):
        from django.db import IntegrityError
        make_mission()
        with pytest.raises(IntegrityError), transaction.atomic():
            make_mission()


@pytest.mark.geo
@pytest.mark.django_db(transaction=True)
def test_advance_refuses_outside_a_transaction(robot, make_mission):
    """Not in TestAdvance: pytest-django wraps those in atomic(), which would
    hide exactly the mistake this guards against."""
    make_mission()
    with pytest.raises(RuntimeError):
        advance(robot, pt(), timezone.now())


# ── ros_ingest hook ──────────────────────────────────────────────────────

def _fix(north_m=0.0, east_m=0.0, status=0):
    lat, lon = at(north_m, east_m)
    t = time.time()
    return {"header": {"stamp": {"sec": int(t), "nanosec": int((t % 1) * 1e9)}},
            "status": {"status": status}, "latitude": lat, "longitude": lon}


@pytest.fixture
def cmd(robot, monkeypatch):
    monkeypatch.setattr(mod, "close_old_connections", lambda: None)
    monkeypatch.setattr(mod, "broadcast_sensorlog", lambda log: None)
    c = mod.Command()
    c.robot, c.source, c.max_skew, c.note = robot, SensorLog.Source.SIMULATED, 120.0, "test"
    c.region, c.counts, c.lock, c.broadcast_up = KENYA_BBOX, Counter(), threading.Lock(), True
    c.readings = mod.ReadingCache(ceiling=c.source)
    return c


@pytest.mark.geo
@pytest.mark.django_db
class TestIngestHook:

    def test_fix_completes_and_row_joins_mission(self, cmd, make_mission):
        m = make_mission()
        cmd._ingest(_fix(north_m=2.0))
        log = SensorLog.objects.get()
        assert log.mission_id == m.pk
        assert statuses(m) == [C, P, P]
        assert m.waypoints.get(order=0).completed_at == log.timestamp
        assert cmd.counts["wp_completed"] == 1

    def test_route_through_ingest_completes_mission(self, cmd, make_mission):
        m = make_mission()
        for north in (0.0, 25.0, 50.0, 75.0, 100.0):
            cmd._ingest(_fix(north_m=north))
        m.refresh_from_db()
        assert m.status == Mission.Status.COMPLETED
        assert SensorLog.objects.filter(mission=m).count() == 5, "the completing fix is attached too"
        assert (cmd.counts["wp_completed"], cmd.counts["mission_completed"]) == (3, 1)

    def test_no_mission_row_has_none(self, cmd):
        cmd._ingest(_fix())
        assert SensorLog.objects.get().mission_id is None

    def test_skipped_fix_never_advances(self, cmd, make_mission):
        m = make_mission()
        cmd._ingest(_fix(status=-1))                      # no_fix, right on wp1
        assert statuses(m) == [P, P, P] and SensorLog.objects.count() == 0

    def test_failed_row_rolls_back_the_advance(self, cmd, make_mission, monkeypatch):
        m = make_mission()
        def boom(*a, **k):
            raise RuntimeError("db write failed")
        monkeypatch.setattr(SensorLog.objects, "create", boom)
        with pytest.raises(RuntimeError):
            cmd._ingest(_fix())
        assert statuses(m) == [P, P, P], "no row, no completion"


# ── Start ────────────────────────────────────────────────────────────────

def start(client, m):
    return client.post(reverse("mission-start", args=[m.pk]), format="json")


@pytest.fixture
def launcher(org):
    u = get_user_model().objects.create_user(username="launcher", password="LauncherPassword1234!", organization=org)
    call_command("grant_launch", "launcher", stdout=open("/dev/null", "w"))
    c = APIClient()
    c.force_authenticate(user=get_user_model().objects.get(pk=u.pk))
    return c


@pytest.mark.geo
@pytest.mark.django_db
class TestStart:

    def test_start_sets_in_progress_and_started_at(self, launcher, make_mission):
        m = make_mission(status=Mission.Status.PENDING)
        r = start(launcher, m)
        assert r.status_code == 200 and r.data["status"] == "IN_PROGRESS"
        m.refresh_from_db()
        assert m.status == Mission.Status.IN_PROGRESS and m.started_at is not None

    def test_without_permission_403_unchanged(self, authed_client, make_mission):
        m = make_mission(status=Mission.Status.PENDING)
        assert start(authed_client, m).status_code == 403
        m.refresh_from_db()
        assert m.status == Mission.Status.PENDING

    def test_other_tenant_404_even_with_permission(self, other_org, other_robot, launcher, make_mission):
        theirs = make_mission(status=Mission.Status.PENDING, robot=other_robot, organization=other_org)
        assert start(launcher, theirs).status_code == 404

    @pytest.mark.parametrize("st", ["IN_PROGRESS", "PAUSED", "COMPLETED", "ABORTED"])
    def test_not_pending_409(self, launcher, make_mission, st):
        assert start(launcher, make_mission(status=st)).status_code == 409

    def test_second_running_mission_on_same_robot_409(self, launcher, make_mission):
        make_mission()  # already running
        m2 = make_mission(status=Mission.Status.PENDING)
        r = start(launcher, m2)
        assert r.status_code == 409 and "already" in r.data["detail"]
        m2.refresh_from_db()
        assert m2.status == Mission.Status.PENDING

    def test_other_robot_can_run_concurrently(self, launcher, org, make_mission):
        bot2 = Robot.objects.create(organization=org, name="Bot 2", robot_id_str="TEST-BOT-002")
        make_mission()
        assert start(launcher, make_mission(status=Mission.Status.PENDING, robot=bot2)).status_code == 200

    def test_grant_launch_revoke(self, org):
        u = get_user_model().objects.create_user(username="x", password="XPassword1234!", organization=org)
        call_command("grant_launch", "x", stdout=open("/dev/null", "w"))
        assert get_user_model().objects.get(pk=u.pk).has_perm("missions.launch_mission")
        call_command("grant_launch", "x", "--revoke", stdout=open("/dev/null", "w"))
        assert not get_user_model().objects.get(pk=u.pk).has_perm("missions.launch_mission")
# ─── RANGER V3 END: 15-mission-advance ───
