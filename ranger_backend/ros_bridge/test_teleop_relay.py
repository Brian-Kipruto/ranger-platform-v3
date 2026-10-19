# ─── RANGER V3 START: 14-teleop ───
"""F14 5a step 2: teleop commands and the relay (channel layer -> /ranger/cmd_vel).

The point: the relay publishes exactly the fresh, valid commands it receives, once
each, and never replays a stale queue. In-memory channel layer; roslibpy faked.
"""
import math
import re
import time

import pytest
from channels.layers import get_channel_layer
from django.core.management import call_command
from django.core.management.base import CommandError

from ros_bridge.management.commands import teleop_relay as relay_cmd
from ros_bridge.teleop import (
    MAX_CMD_AGE_S,
    TELEOP_CMD,
    make_cmd,
    relay_one,
    teleop_channel,
    twist,
    validate_cmd,
)


@pytest.fixture(autouse=True)
def in_memory_layer(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


NOW = 1_000_000.0


# ── names and commands ───────────────────────────────────────────────────────
def test_channel_is_valid_and_per_robot():
    assert teleop_channel(3) == "teleop.robot.3"
    assert teleop_channel(3) != teleop_channel(4)
    assert re.fullmatch(r"[a-zA-Z0-9\-_.]+", teleop_channel(123456)) and len(teleop_channel(1)) < 100


def test_make_and_validate_round_trip():
    msg = make_cmd(0.6, -0.25, NOW)
    assert msg == {"type": TELEOP_CMD, "lin": 0.6, "ang": -0.25, "sent_at": NOW}
    assert validate_cmd(msg, NOW + 0.02) == ((0.6, -0.25), None)


@pytest.mark.parametrize("lin, ang", [(1.01, 0), (0, -1.01), (math.nan, 0), (0, math.inf),
                                      ("0.5", 0), (True, 0), (None, 0)])
def test_make_cmd_refuses_what_the_relay_would_drop(lin, ang):
    with pytest.raises(ValueError):
        make_cmd(lin, ang, NOW)


def test_bounds_inclusive():
    assert validate_cmd(make_cmd(1, -1, NOW), NOW)[0] == (1.0, -1.0)


@pytest.mark.parametrize("msg, reason", [
    ("not a dict", "type"),
    ({"type": "sensorlog", "lin": 0, "ang": 0, "sent_at": NOW}, "type"),
    ({"type": TELEOP_CMD, "lin": 2, "ang": 0, "sent_at": NOW}, "value"),
    ({"type": TELEOP_CMD, "lin": float("nan"), "ang": 0, "sent_at": NOW}, "value"),
    ({"type": TELEOP_CMD, "lin": False, "ang": 0, "sent_at": NOW}, "value"),
    ({"type": TELEOP_CMD, "ang": 0, "sent_at": NOW}, "value"),
    ({"type": TELEOP_CMD, "lin": 0, "ang": 0}, "sent_at"),
    ({"type": TELEOP_CMD, "lin": 0, "ang": 0, "sent_at": "now"}, "sent_at"),
    ({"type": TELEOP_CMD, "lin": 0, "ang": 0, "sent_at": float("inf")}, "sent_at"),
])
def test_validate_rejects(msg, reason):
    assert validate_cmd(msg, NOW) == (None, reason)


def test_freshness_window():
    msg = make_cmd(0.5, 0, 0.0)            # sent_at 0.0 keeps the float arithmetic exact
    assert validate_cmd(msg, MAX_CMD_AGE_S)[0] == (0.5, 0.0)                  # inclusive
    assert validate_cmd(msg, MAX_CMD_AGE_S + 0.001) == (None, "stale")
    assert validate_cmd(msg, -0.04)[0] == (0.5, 0.0)                          # tiny skew ok
    assert validate_cmd(msg, -0.2) == (None, "future")


def test_twist_shape():
    t = twist(0.6, -0.3)
    assert t["linear"] == {"x": 0.6, "y": 0.0, "z": 0.0}
    assert t["angular"] == {"x": 0.0, "y": 0.0, "z": -0.3}


# ── relay_one ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_relay_publishes_fresh_command_once():
    layer, ch, sent = get_channel_layer(), teleop_channel(1), []
    await layer.send(ch, make_cmd(0.6, 0.0, time.time()))
    assert await relay_one(layer, ch, sent.append, time.time) == "sent"
    assert sent == [twist(0.6, 0.0)]


@pytest.mark.asyncio
async def test_relay_never_replays_a_stale_queue():
    # Commands queued while no relay ran, then a relay starts: none of the old ones drive.
    layer, ch, sent = get_channel_layer(), teleop_channel(1), []
    for i in range(5):
        await layer.send(ch, make_cmd(1.0, 0.0, NOW + i * 0.05))
    outcomes = [await relay_one(layer, ch, sent.append, lambda: NOW + 60) for _ in range(5)]
    assert outcomes == ["stale"] * 5 and sent == []
    await layer.send(ch, make_cmd(0.2, 0.0, NOW + 60))
    assert await relay_one(layer, ch, sent.append, lambda: NOW + 60.01) == "sent"
    assert sent == [twist(0.2, 0.0)]


@pytest.mark.asyncio
async def test_relay_drops_malformed():
    layer, ch, sent = get_channel_layer(), teleop_channel(1), []
    await layer.send(ch, {"type": TELEOP_CMD, "lin": 5, "ang": 0, "sent_at": time.time()})
    assert await relay_one(layer, ch, sent.append, time.time) == "value"
    assert sent == []


@pytest.mark.asyncio
async def test_relay_reads_only_its_robot():
    layer, sent = get_channel_layer(), []
    await layer.send(teleop_channel(2), make_cmd(0.9, 0.0, time.time()))
    await layer.send(teleop_channel(1), make_cmd(0.1, 0.0, time.time()))
    assert await relay_one(layer, teleop_channel(1), sent.append, time.time) == "sent"
    assert sent == [twist(0.1, 0.0)]


# ── the command ──────────────────────────────────────────────────────────────
class FakeRos:
    instances = []

    def __init__(self, host, port):
        self.host, self.port, self.terminated = host, port, False
        FakeRos.instances.append(self)

    def run(self, timeout):
        pass

    def terminate(self):
        self.terminated = True


class FakeTopic:
    instances = []

    def __init__(self, client, name, msg_type):
        self.name, self.msg_type, self.published, self.advertised = name, msg_type, [], False
        FakeTopic.instances.append(self)

    def advertise(self):
        self.advertised = True

    def unadvertise(self):
        self.advertised = False

    def publish(self, msg):
        self.published.append(dict(msg.data))


@pytest.fixture
def fake_ros(monkeypatch):
    FakeRos.instances, FakeTopic.instances = [], []
    monkeypatch.setattr(relay_cmd.roslibpy, "Ros", FakeRos)
    monkeypatch.setattr(relay_cmd.roslibpy, "Topic", FakeTopic)
    monkeypatch.setattr(relay_cmd.time, "sleep", lambda s: None)


@pytest.mark.django_db
def test_command_unknown_robot(fake_ros):
    with pytest.raises(CommandError, match="No robot"):
        call_command("teleop_relay", robot="NOPE-404")
    assert FakeRos.instances == []  # failed before touching the network


@pytest.mark.django_db
def test_command_relays_then_publishes_stop_on_exit(fake_ros, robot):
    from asgiref.sync import async_to_sync
    layer, ch = get_channel_layer(), teleop_channel(robot.pk)
    async_to_sync(layer.send)(ch, make_cmd(1.0, 0.0, time.time() - 30))   # stale: dropped
    async_to_sync(layer.send)(ch, make_cmd(0.6, -0.2, time.time()))
    call_command("teleop_relay", robot=robot.robot_id_str, max_messages=2)
    topic = FakeTopic.instances[0]
    assert topic.name == "/ranger/cmd_vel" and topic.msg_type == "geometry_msgs/msg/Twist"
    assert topic.published == [twist(0.6, -0.2), twist(0.0, 0.0)]
    assert FakeRos.instances[0].terminated
# ─── RANGER V3 END: 14-teleop ───
