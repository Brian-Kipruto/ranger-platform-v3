# ─── RANGER V3 START: 09-live-console ───
"""
F09 2b: ros_ingest broadcasts every saved row, and only saved rows; a broadcast
failure never costs a row.

Drives Command._ingest directly with rosbridge-shaped dicts, so neither the
Orin nor Redis is needed. Broadcast is patched at the name ros_ingest imports.
"""
import threading
import time
from collections import Counter

import pytest

from core.geo import KENYA_BBOX
from core.models import SensorLog
from ros_bridge.management.commands import ros_ingest as mod

pytestmark = pytest.mark.django_db


def _fix(lat=-1.2864, lon=36.8172, status=0, stamp=None):
    t = time.time() if stamp is None else stamp
    return {
        "header": {"stamp": {"sec": int(t), "nanosec": int((t % 1) * 1e9)}},
        "status": {"status": status},
        "latitude": lat,
        "longitude": lon,
    }


@pytest.fixture(autouse=True)
def keep_test_connection(monkeypatch):
    """_ingest calls close_old_connections() (right for a long-running
    process). Inside pytest's per-test transaction that kills the connection,
    so neutralise it here only."""
    monkeypatch.setattr(mod, "close_old_connections", lambda: None)


@pytest.fixture
def cmd(robot):
    c = mod.Command()
    c.robot = robot
    c.source = SensorLog.Source.SIMULATED
    c.max_skew = 120.0
    c.note = "test"
    c.region = KENYA_BBOX  # F11: _ingest reads the resolved region
    c.counts = Counter()
    c.lock = threading.Lock()
    c.broadcast_up = True
    return c


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "broadcast_sensorlog", calls.append)
    return calls


def test_saved_row_is_broadcast(cmd, sent):
    cmd._ingest(_fix())
    log = SensorLog.objects.get()
    assert [l.pk for l in sent] == [log.pk]
    assert cmd.counts == Counter(saved=1, broadcast=1)


def test_skipped_fixes_are_not_broadcast(cmd, sent):
    cmd._ingest(_fix(status=-1))                     # no_fix
    cmd._ingest(_fix(lat=None))                      # no_coords
    cmd._ingest(_fix(stamp=time.time() - 3600))      # clock_skew
    cmd._ingest(_fix(lat=36.8172, lon=-1.2864))      # out_of_region (inverted)
    assert sent == []
    assert SensorLog.objects.count() == 0


def test_broadcast_failure_keeps_rows_and_counts(cmd, monkeypatch):
    def down(log):
        raise ConnectionError("redis down")
    monkeypatch.setattr(mod, "broadcast_sensorlog", down)

    cmd._ingest(_fix())
    cmd._ingest(_fix())
    assert SensorLog.objects.count() == 2
    assert cmd.counts == Counter(saved=2, broadcast_error=2)
    assert cmd.broadcast_up is False


def test_broadcast_recovers(cmd, monkeypatch):
    up = {"ok": False}
    def flaky(log):
        if not up["ok"]:
            raise ConnectionError("redis down")
    monkeypatch.setattr(mod, "broadcast_sensorlog", flaky)

    cmd._ingest(_fix())
    up["ok"] = True
    cmd._ingest(_fix())
    assert cmd.counts == Counter(saved=2, broadcast_error=1, broadcast=1)
    assert cmd.broadcast_up is True
# ─── RANGER V3 END: 09-live-console ───
