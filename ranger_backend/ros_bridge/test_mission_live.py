# ─── RANGER V3 START: 15-mission-live ───
"""
F15 6c: mission.progress over the dashboard socket.

  * tenancy: a completion in org A reaches A's socket and NOTHING reaches B's
    (real ASGI app, in-memory layer — same harness as test_consumers);
  * both writers emit it only when a waypoint completed, after the row;
  * a dead layer never blocks the row or the completion.

Mutation checks (run by hand, each must turn a test red):
  * drop DashboardConsumer.mission_progress            -> test_progress_reaches_own_org_only
  * emit on every row (drop `if adv and adv.completed`) -> test_ingest_emits_only_on_completion
"""
import io
import math
import threading
import time
from collections import Counter

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from core.geo import KENYA_BBOX, point_from_latlon
from core.management.commands import run_simulation as sim_mod
from core.models import SensorLog
from missions.models import Mission, Waypoint
from missions.progress import advance
from ranger_backend.asgi import application
from ros_bridge.broadcast import broadcast_mission_progress, mission_progress_payload
from ros_bridge.consumers import SUBPROTOCOL
from ros_bridge.management.commands import ros_ingest as ingest_mod

BASE = (-1.2864, 36.8172)


def at(north_m=0.0, east_m=0.0):
    lat, lon = BASE
    return lat + north_m / 111_320.0, lon + east_m / (111_320.0 * math.cos(math.radians(lat)))


def make_mission(org, robot, offsets=((0, 0), (50, 0))):
    m = Mission.objects.create(organization=org, robot=robot, name="live",
                               status=Mission.Status.IN_PROGRESS)
    for i, (n, e) in enumerate(offsets):
        lat, lon = at(n, e)
        Waypoint.objects.create(mission=m, order=i, location=point_from_latlon(lat=lat, lon=lon))
    return m


def complete_first(robot):
    lat, lon = at(1, 0)
    with transaction.atomic():
        return advance(robot, point_from_latlon(lat=lat, lon=lon), timezone.now())


# ── payload ──────────────────────────────────────────────────────────────

@pytest.mark.geo
@pytest.mark.django_db
def test_payload_shape(org, robot):
    m = make_mission(org, robot)
    adv = complete_first(robot)
    p = mission_progress_payload(adv)
    assert p["type"] == "mission.progress"
    assert (p["mission"], p["robot"], p["mission_status"]) == (m.pk, robot.robot_id_str, "IN_PROGRESS")
    assert (p["waypoint"]["order"], p["waypoint"]["status"]) == (0, "COMPLETED")
    assert p["waypoint"]["completed_at"].endswith("Z")
    assert p["distance_m"] == pytest.approx(1.0, abs=0.1)


# ── tenancy over the real socket ─────────────────────────────────────────

@pytest.fixture
def in_memory_layer(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@pytest_asyncio.fixture
async def close_worker_db_connections():
    yield
    await sync_to_async(connections.close_all)()


def _sock_for(username, org):
    u = get_user_model().objects.create_user(username=username, password="Pw-for-tests-1234!", organization=org)
    token = str(AccessToken.for_user(u))
    return WebsocketCommunicator(application, "/ws/dashboard/",
                                 headers=[(b"origin", b"http://localhost:5173")],
                                 subprotocols=[SUBPROTOCOL, f"jwt.{token}"])


@pytest.mark.geo
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_progress_reaches_own_org_only(org, other_org, robot, in_memory_layer, close_worker_db_connections):
    a = await sync_to_async(_sock_for)("alice", org)
    b = await sync_to_async(_sock_for)("bob", other_org)
    assert (await a.connect())[0] and (await b.connect())[0]

    def complete_and_send():
        make_mission(org, robot)
        adv = complete_first(robot)
        broadcast_mission_progress(adv)
        return adv
    adv = await sync_to_async(complete_and_send)()

    msg = await a.receive_json_from(timeout=2)
    assert msg["type"] == "mission.progress" and msg["mission"] == adv.mission.pk
    assert msg["waypoint"]["status"] == "COMPLETED"
    assert await b.receive_nothing(timeout=0.5), "org B received org A's mission progress"
    await a.disconnect()
    await b.disconnect()


# ── ros_ingest emits only on completion, after the row ───────────────────

def _fix(north_m=0.0):
    lat, lon = at(north_m, 0)
    t = time.time()
    return {"header": {"stamp": {"sec": int(t), "nanosec": int((t % 1) * 1e9)}},
            "status": {"status": 0}, "latitude": lat, "longitude": lon}


@pytest.fixture
def cmd(robot, monkeypatch):
    events = []
    monkeypatch.setattr(ingest_mod, "close_old_connections", lambda: None)
    monkeypatch.setattr(ingest_mod, "broadcast_sensorlog", lambda log: events.append(("row", log.pk)))
    monkeypatch.setattr(ingest_mod, "broadcast_mission_progress",
                        lambda adv: events.append(("progress", adv.waypoint.order)))
    c = ingest_mod.Command()
    c.robot, c.source, c.max_skew, c.note = robot, SensorLog.Source.SIMULATED, 120.0, "test"
    c.region, c.counts, c.lock, c.broadcast_up = KENYA_BBOX, Counter(), threading.Lock(), True
    c.readings = ingest_mod.ReadingCache(ceiling=c.source)
    c.events = events
    return c


@pytest.mark.geo
@pytest.mark.django_db
def test_ingest_emits_only_on_completion(cmd, org, robot):
    make_mission(org, robot)
    for north in (-20, -10, 0, 25, 50, 60):
        cmd._ingest(_fix(north))
    progress = [e for e in cmd.events if e[0] == "progress"]
    assert progress == [("progress", 0), ("progress", 1)]
    # each progress event follows its own row's broadcast
    i0 = cmd.events.index(("progress", 0))
    assert cmd.events[i0 - 1][0] == "row"
    assert cmd.counts["progress_broadcast"] == 2


@pytest.mark.geo
@pytest.mark.django_db
def test_ingest_progress_failure_keeps_row_and_completion(cmd, org, robot, monkeypatch):
    m = make_mission(org, robot)

    def down(adv):
        raise ConnectionError("redis down")
    monkeypatch.setattr(ingest_mod, "broadcast_mission_progress", down)
    cmd._ingest(_fix(0))
    assert SensorLog.objects.count() == 1
    assert m.waypoints.get(order=0).status == Waypoint.Status.COMPLETED
    assert cmd.counts["progress_broadcast_error"] == 1


# ── run_simulation --live emits too ──────────────────────────────────────

@pytest.mark.geo
@pytest.mark.django_db
def test_run_simulation_live_emits_progress(org, robot, monkeypatch):
    make_mission(org, robot, offsets=((0, 0), (40, 0), (40, 40)))
    sent = []
    monkeypatch.setattr(sim_mod, "broadcast_sensorlog", lambda log: None)
    monkeypatch.setattr(sim_mod, "broadcast_mission_progress",
                        lambda adv: sent.append((adv.waypoint.order, adv.mission_completed)))
    calls = {"n": 0}

    def stop(_):
        calls["n"] += 1
        if calls["n"] >= 40:
            raise KeyboardInterrupt
    monkeypatch.setattr(sim_mod.time, "sleep", stop)
    call_command("run_simulation", robot_id_str=robot.robot_id_str, live=True, live_delay=1.0,
                 speed=5.0, seed=7, stdout=io.StringIO(), stderr=io.StringIO())
    assert sent == [(0, False), (1, False), (2, True)]


@pytest.mark.geo
@pytest.mark.django_db
def test_run_simulation_backfill_never_broadcasts(org, robot, monkeypatch):
    make_mission(org, robot)

    def boom(*_):
        raise AssertionError("backfill must not broadcast")
    monkeypatch.setattr(sim_mod, "broadcast_sensorlog", boom)
    monkeypatch.setattr(sim_mod, "broadcast_mission_progress", boom)
    call_command("run_simulation", robot_id_str=robot.robot_id_str, count=20, interval_seconds=5,
                 speed=2.0, seed=7, stdout=io.StringIO())
    assert Mission.objects.get().status == Mission.Status.COMPLETED


# ─── RANGER V3 END: 15-mission-live ───
