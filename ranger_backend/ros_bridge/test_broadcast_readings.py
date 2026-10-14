# ─── RANGER V3 START: 13-console-readings ───
"""The live payload carries each reading with its own source (F13 5d, ADR-0020).

The console's SIM chip on radiation is only as honest as this payload: the
row's `source` is the position's, and a live robot with a simulated tube must
arrive as source=live + readings.radiation.source=simulated.
"""
import json
import threading
import time
from collections import Counter

import pytest

from core.geo import KENYA_BBOX
from core.models import AirQualityLog, ImuBaroLog, RadiationLog, SensorLog
from ros_bridge import broadcast
from ros_bridge.management.commands import ros_ingest as ingest

S = SensorLog.Source
pytestmark = pytest.mark.django_db


@pytest.fixture
def live_row(sensor_log_at):
    log = sensor_log_at(-1.2864, 36.8172)
    log.source = S.LIVE
    log.save(update_fields=["source"])
    return log


def payload_of(log):
    """As broadcast_sensorlog builds it, from a fresh DB read (no caches)."""
    return broadcast.sensorlog_payload(SensorLog.objects.get(pk=log.pk))


def test_row_without_readings_has_empty_readings_and_old_keys_intact(live_row):
    p = payload_of(live_row)
    assert p["readings"] == {}
    assert {k: p[k] for k in ("type", "id", "source")} == \
        {"type": "sensorlog", "id": live_row.pk, "source": "live"}
    assert isinstance(p["lat"], float) and isinstance(p["lon"], float)


def test_mixed_row_each_reading_keeps_its_own_label(live_row):
    RadiationLog.objects.create(sensor_log=live_row, radiation_value=31.0,
                                dose_rate_usvh=None, source=S.SIMULATED)
    ImuBaroLog.objects.create(sensor_log=live_row, roll=2.4, pitch=-9.5, yaw=None,
                              pressure_baro=831.6, altitude_baro=1635.2, source=S.LIVE)
    p = payload_of(live_row)
    assert p["source"] == "live"
    assert p["readings"] == {
        "radiation": {"cpm": 31.0, "dose_rate_usvh": None, "source": "simulated"},
        "imu_baro": {"roll": 2.4, "pitch": -9.5, "yaw": None, "pressure_hpa": 831.6,
                     "altitude_m": 1635.2, "source": "live"},
    }
    assert "air_quality" not in p["readings"]  # absent, not zero


def test_air_quality_shape(live_row):
    AirQualityLog.objects.create(sensor_log=live_row, pm25=16.7, pm10=29.9, source=S.SIMULATED)
    assert payload_of(live_row)["readings"]["air_quality"] == \
        {"pm25": 16.7, "pm10": 29.9, "source": "simulated"}


def test_payload_is_strict_json(live_row):
    """No NaN on the wire: browsers' JSON.parse rejects it."""
    RadiationLog.objects.create(sensor_log=live_row, radiation_value=30.0, source=S.SIMULATED)
    ImuBaroLog.objects.create(sensor_log=live_row, yaw=None, source=S.LIVE)
    json.dumps(payload_of(live_row), allow_nan=False)


def test_ingest_broadcasts_the_readings_it_just_attached(robot, monkeypatch):
    """Through the real ingest path: the broadcast is built after the row's
    transaction, so the readings it attached are in the payload."""
    sent = []
    monkeypatch.setattr(ingest, "close_old_connections", lambda: None)
    monkeypatch.setattr(ingest, "broadcast_sensorlog",
                        lambda log: sent.append(broadcast.sensorlog_payload(log)))
    c = ingest.Command()
    c.robot, c.source, c.max_skew, c.note = robot, S.LIVE, 120.0, "test"
    c.region = KENYA_BBOX
    c.counts, c.lock, c.broadcast_up = Counter(), threading.Lock(), True
    c.readings = ingest.ReadingCache(ceiling=S.LIVE)

    hdr = {"stamp": {"sec": int(time.time()), "nanosec": 0}}
    c._dispatch(("radiation", {"header": hdr, "cpm": 33.0, "dose_rate_usvh": None,
                               "source": "simulated"}))
    c._dispatch(("imu_baro", {"header": hdr, "roll": 1.0, "pitch": 2.0, "yaw": None,
                              "pressure_hpa": 831.0, "altitude_m": 1640.0, "source": "live"}))
    c._dispatch(("fix", {"header": hdr, "status": {"status": 0},
                         "latitude": -1.2864, "longitude": 36.8172}))

    assert len(sent) == 1
    p = sent[0]
    assert p["source"] == "live"
    assert p["readings"]["radiation"]["source"] == "simulated"
    assert p["readings"]["imu_baro"]["source"] == "live"
    assert p["readings"]["imu_baro"]["yaw"] is None
    assert "air_quality" not in p["readings"]
# ─── RANGER V3 END: 13-console-readings ───
