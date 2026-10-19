# ─── RANGER V3 START: 14-teleop ───
"""F14 5a step 3: TeleopConsumer. Who may drive, one driver per robot, and what reaches
the relay's channel.

Real ASGI application (origin validator + router + consumer), in-memory channel layer,
in-memory drive lock. transaction=True for the same reason as test_consumers.
"""
import time
from datetime import timedelta

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from rest_framework_simplejwt.tokens import AccessToken

from ranger_backend.asgi import application
from ros_bridge.consumers import CLOSE_NO_ORG, CLOSE_UNAUTHENTICATED, SUBPROTOCOL
from ros_bridge.drive_lock import MemoryDriveLock
from ros_bridge.teleop import TELEOP_CMD, teleop_channel, validate_cmd
from ros_bridge.teleop_consumer import (
    CLOSE_NO_ROBOT,
    CLOSE_NOT_DRIVER,
    CLOSE_ROBOT_BUSY,
    MAX_MSGS_PER_S,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

ORIGIN = [(b"origin", b"http://localhost:5173")]


@pytest.fixture(autouse=True)
def isolated(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    settings.TELEOP_DRIVE_LOCK = "memory"
    MemoryDriveLock._held.clear()
    yield
    MemoryDriveLock._held.clear()


@pytest_asyncio.fixture(autouse=True)
async def close_worker_db_connections():
    yield
    await sync_to_async(connections.close_all)()


def _user(username, org, *, driver=False, superuser=False):
    u = get_user_model().objects.create_user(
        username=username, password="Pw-for-tests-1234!", organization=org,
        is_superuser=superuser)
    if driver:
        call_command("grant_drive", username, stdout=open("/dev/null", "w"))
    return u


def _token(user, **exp):
    t = AccessToken.for_user(user)
    if exp:
        t.set_exp(lifetime=timedelta(**exp))
    return str(t)


async def _make(username, org, **kw):
    return await sync_to_async(lambda: _token(_user(username, org, **kw)))()


def _sock(robot_id, token=None):
    protocols = [SUBPROTOCOL] + ([f"jwt.{token}"] if token else [])
    return WebsocketCommunicator(application, f"/ws/teleop/{robot_id}/",
                                 headers=ORIGIN, subprotocols=protocols)


async def _closed_with(sock):
    connected, _ = await sock.connect()
    assert connected, "consumer must accept before closing so the code reaches the browser"
    msg = await sock.receive_output(timeout=2)
    assert msg["type"] == "websocket.close"
    await sock.wait()
    return msg["code"]


async def _ready(sock):
    connected, proto = await sock.connect()
    assert connected and proto == SUBPROTOCOL
    assert await sock.receive_json_from(timeout=2) == {"type": "ready", "robot": sock.scope["path"].split("/")[3]}
    return sock


async def _next_cmd(robot_pk, timeout=1.0):
    import asyncio
    return await asyncio.wait_for(get_channel_layer().receive(teleop_channel(robot_pk)), timeout)


async def _no_cmd(robot_pk):
    import asyncio
    with pytest.raises(asyncio.TimeoutError):
        await _next_cmd(robot_pk, timeout=0.2)


# ── who may drive ────────────────────────────────────────────────────────────
async def test_no_token(robot):
    assert await _closed_with(_sock(robot.robot_id_str)) == CLOSE_UNAUTHENTICATED


async def test_expired_token(org, robot):
    token = await sync_to_async(lambda: _token(_user("ex", org, driver=True), seconds=-1))()
    assert await _closed_with(_sock(robot.robot_id_str, token)) == CLOSE_UNAUTHENTICATED


async def test_garbage_token(robot):
    assert await _closed_with(_sock(robot.robot_id_str, "not.a.jwt")) == CLOSE_UNAUTHENTICATED


async def test_user_without_org(robot):
    token = await _make("orphan", None, driver=True)
    assert await _closed_with(_sock(robot.robot_id_str, token)) == CLOSE_NO_ORG


async def test_unknown_robot(org):
    token = await _make("d", org, driver=True)
    assert await _closed_with(_sock("NOPE-404", token)) == CLOSE_NO_ROBOT


async def test_other_orgs_robot_looks_unknown(org, other_robot):
    token = await _make("d", org, driver=True)
    assert await _closed_with(_sock(other_robot.robot_id_str, token)) == CLOSE_NO_ROBOT


async def test_member_without_drive_permission(org, robot):
    token = await _make("viewer", org)
    assert await _closed_with(_sock(robot.robot_id_str, token)) == CLOSE_NOT_DRIVER


async def test_driver_via_group(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.disconnect()


async def test_superuser_drives_without_group(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("su", org, superuser=True)))
    await sock.disconnect()


async def test_revoke_takes_effect_on_next_connect(org, robot):
    token = await _make("d", org, driver=True)
    await sync_to_async(call_command)("grant_drive", "d", revoke=True, stdout=open("/dev/null", "w"))
    assert await _closed_with(_sock(robot.robot_id_str, token)) == CLOSE_NOT_DRIVER


# ── one driver per robot ─────────────────────────────────────────────────────
async def test_second_driver_refused_then_allowed_after_release(org, robot):
    a = await _ready(_sock(robot.robot_id_str, await _make("a", org, driver=True)))
    token_b = await _make("b", org, driver=True)
    assert await _closed_with(_sock(robot.robot_id_str, token_b)) == CLOSE_ROBOT_BUSY
    await a.disconnect()
    b = await _ready(_sock(robot.robot_id_str, token_b))
    await b.disconnect()


async def test_lease_lost_closes_the_session(org, robot):
    a = await _ready(_sock(robot.robot_id_str, await _make("a", org, driver=True)))
    MemoryDriveLock._held.clear()                       # lease lapsed...
    await MemoryDriveLock().acquire(robot.pk, "someone-else")   # ...and was taken
    await a.send_json_to({"type": "drive", "lin": 0.5, "ang": 0.0})
    msg = await a.receive_output(timeout=1)
    assert msg == {"type": "websocket.close", "code": CLOSE_ROBOT_BUSY}
    await _no_cmd(robot.pk)                              # nothing forwarded


async def test_different_robots_drive_independently(org, robot, sensor_types):
    from core.models import Robot
    r2 = await sync_to_async(Robot.objects.create)(organization=org, name="Two", robot_id_str="RANGER-TWO-002")
    a = await _ready(_sock(robot.robot_id_str, await _make("a", org, driver=True)))
    b = await _ready(_sock(r2.robot_id_str, await _make("b", org, driver=True)))
    await a.disconnect()
    await b.disconnect()


# ── what reaches the relay ───────────────────────────────────────────────────
async def test_drive_forwarded_fresh_and_valid(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to({"type": "drive", "lin": 0.6, "ang": -0.2})
    msg = await _next_cmd(robot.pk)
    assert msg["type"] == TELEOP_CMD and (msg["lin"], msg["ang"]) == (0.6, -0.2)
    assert validate_cmd(msg, time.time())[0] == (0.6, -0.2)   # the relay would accept it
    await sock.disconnect()


@pytest.mark.parametrize("bad", [
    {"type": "drive", "lin": 1.5, "ang": 0},
    {"type": "drive", "lin": "fast", "ang": 0},
    {"type": "drive", "lin": True, "ang": 0},
    {"type": "drive", "ang": 0},
])
async def test_bad_values_never_forwarded(org, robot, bad):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to(bad)
    assert await sock.receive_json_from(timeout=1) == {"type": "error", "reason": "value"}
    await _no_cmd(robot.pk)
    await sock.disconnect()


@pytest.mark.parametrize("bad", [{"type": "teleport"}, {"lin": 0.5, "ang": 0}, [1, 2]])
async def test_unknown_messages_never_forwarded(org, robot, bad):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to(bad)
    assert await sock.receive_json_from(timeout=1) == {"type": "error", "reason": "bad_message"}
    await _no_cmd(robot.pk)
    await sock.disconnect()


async def test_hold_forwards_nothing(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to({"type": "hold"})
    await _no_cmd(robot.pk)
    await sock.disconnect()


async def test_stop_forwards_zero(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to({"type": "stop"})
    msg = await _next_cmd(robot.pk)
    assert (msg["lin"], msg["ang"]) == (0.0, 0.0)
    await sock.disconnect()


async def test_disconnect_sends_one_zero_and_releases(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    await sock.send_json_to({"type": "drive", "lin": 0.6, "ang": 0.0})
    assert (await _next_cmd(robot.pk))["lin"] == 0.6
    await sock.disconnect()
    msg = await _next_cmd(robot.pk)
    assert (msg["lin"], msg["ang"]) == (0.0, 0.0)
    await _no_cmd(robot.pk)
    assert MemoryDriveLock._held == {}


async def test_refused_session_sends_nothing(org, robot):
    token = await _make("viewer", org)
    assert await _closed_with(_sock(robot.robot_id_str, token)) == CLOSE_NOT_DRIVER
    await _no_cmd(robot.pk)          # not even the disconnect zero


async def test_rate_limited(org, robot):
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    for _ in range(MAX_MSGS_PER_S + 5):
        await sock.send_json_to({"type": "hold"})
    errors = 0
    while not await sock.receive_nothing(timeout=0.2):
        assert await sock.receive_json_from() == {"type": "error", "reason": "rate"}
        errors += 1
    assert errors == 5
    await sock.disconnect()


async def test_relay_offline_reported(org, robot, settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer",
                                           "CONFIG": {"capacity": 2}}}
    sock = await _ready(_sock(robot.robot_id_str, await _make("d", org, driver=True)))
    for _ in range(3):
        await sock.send_json_to({"type": "drive", "lin": 0.1, "ang": 0.0})
    assert await sock.receive_json_from(timeout=1) == {"type": "error", "reason": "relay_offline"}
    await sock.disconnect()


# ─── RANGER V3 END: 14-teleop ───
