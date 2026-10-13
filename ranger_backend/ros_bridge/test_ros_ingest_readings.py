# ─── RANGER V3 START: 13-reading-assembly ───
"""F13 5-pre: readings attach to fixes (fork 8) with honest labels (fork 7).

Drives Command._dispatch with rosbridge-shaped (key, msg) items — exactly what
the shared inbox carries — so no Orin, no Redis. Stamps are explicit robot
times, because freshness is judged in robot time, not arrival time.
"""
import threading
import time
from collections import Counter

import pytest

from core.geo import KENYA_BBOX
from core.models import AirQualityLog, ImuBaroLog, RadiationLog, SensorLog
from ros_bridge import readings as rd
from ros_bridge.management.commands import ros_ingest as mod

pytestmark = pytest.mark.django_db
S = SensorLog.Source
# Reset per test by the autouse `quiet` fixture. A module-level time.time()
# ages through a long suite: past ros_ingest's 120 s skew guard every fix is
# rejected (19 spurious failures in a 141 s full run). Helpers read T0 at call
# time, never as a default argument, for the same reason.
T0 = time.time()


def _t(t):
    return T0 if t is None else t


def _hdr(t):
    return {"stamp": {"sec": int(t), "nanosec": int(round((t % 1) * 1e9))}}


def fix(t=None, lat=-1.2864, lon=36.8172, status=0):
    return ("fix", {"header": _hdr(_t(t)), "status": {"status": status},
                    "latitude": lat, "longitude": lon})


def rad(t=None, cpm=31.0, source="simulated", dose=None):
    return ("radiation", {"header": _hdr(_t(t)), "cpm": cpm,
                          "dose_rate_usvh": dose, "source": source})


def pm(t=None, pm25=12.5, pm10=20.0, source="live"):
    return ("air_quality", {"header": _hdr(_t(t)), "pm25": pm25, "pm10": pm10,
                            "source": source})


def imu(t=None, yaw=270.0, source="live", **kw):
    msg = {"header": _hdr(_t(t)), "roll": kw.get("roll", 1.0), "pitch": kw.get("pitch", -2.0),
           "yaw": yaw, "pressure_hpa": kw.get("pressure_hpa", 830.1),
           "altitude_m": kw.get("altitude_m", 1661.0), "source": source}
    return ("imu_baro", msg)


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    global T0
    T0 = time.time()
    monkeypatch.setattr(mod, "close_old_connections", lambda: None)
    monkeypatch.setattr(mod, "broadcast_sensorlog", lambda log: None)


def make_cmd(robot, ceiling):
    c = mod.Command()
    c.robot, c.source, c.max_skew, c.note = robot, ceiling, 120.0, "test"
    c.region = KENYA_BBOX
    c.counts, c.lock, c.broadcast_up = Counter(), threading.Lock(), True
    c.readings = mod.ReadingCache(ceiling=ceiling)
    return c


@pytest.fixture
def live(robot):
    return make_cmd(robot, S.LIVE)


@pytest.fixture
def sim(robot):
    return make_cmd(robot, S.SIMULATED)


def feed(cmd, *items):
    for item in items:
        cmd._dispatch(item)


class TestAttach:

    def test_fresh_readings_land_on_the_fix_row(self, live):
        feed(live, rad(cpm=33.0, dose=0.19), pm(), imu(yaw=271.5), fix())
        log = SensorLog.objects.get()
        assert log.source == S.LIVE
        assert log.radiation_data.radiation_value == 33.0
        assert log.radiation_data.dose_rate_usvh == 0.19
        assert (log.air_quality_data.pm25, log.air_quality_data.pm10) == (12.5, 20.0)
        i = log.imu_baro_data
        assert (i.roll, i.pitch, i.yaw, i.pressure_baro, i.altitude_baro) == \
            (1.0, -2.0, 271.5, 830.1, 1661.0)
        assert live.counts["radiation_attached"] == 1

    def test_reading_without_fix_writes_nothing(self, live):
        feed(live, rad(), pm(), imu())
        assert SensorLog.objects.count() == 0
        assert RadiationLog.objects.count() == 0

    def test_rejected_fix_does_not_consume_readings(self, live):
        feed(live, pm(t=T0), fix(t=T0, status=-1), fix(t=T0 + 1))
        assert SensorLog.objects.count() == 1
        assert AirQualityLog.objects.count() == 1
        assert live.counts["no_fix"] == 1


class TestFreshness:

    @pytest.mark.parametrize("key,item,window", [
        ("radiation", rad, 2.0), ("air_quality", pm, 2.0), ("imu_baro", imu, 1.0),
    ])
    def test_window_edge(self, live, key, item, window):
        """At the window: attaches. 0.05 s past it: does not, and is counted stale."""
        feed(live, item(t=T0 - window), fix(t=T0))
        feed(live, item(t=T0 + 10 - window - 0.05), fix(t=T0 + 10))
        first, second = SensorLog.objects.order_by("timestamp")
        model = {"radiation": RadiationLog, "air_quality": AirQualityLog,
                 "imu_baro": ImuBaroLog}[key]
        assert model.objects.filter(sensor_log=first).exists()
        assert not model.objects.filter(sensor_log=second).exists()
        assert live.counts[f"{key}_stale"] == 1

    def test_stale_reading_is_dropped_not_carried_forward(self, live):
        """An old PM value must not appear on any later fix."""
        feed(live, pm(t=T0 - 5), fix(t=T0), fix(t=T0 + 1))
        assert AirQualityLog.objects.count() == 0
        # Dropped at the first fix, not lingering to be judged again (or to
        # attach to an out-of-order fix later): counted stale exactly once.
        assert "air_quality" not in live.readings.latest
        assert live.counts["air_quality_stale"] == 1

    def test_reading_stamped_ahead_waits_for_its_fix(self, live):
        """Topics interleave across rosbridge: a reading newer than this fix
        (beyond the window) is kept for the next one, not thrown away."""
        feed(live, pm(t=T0 + 3), fix(t=T0), fix(t=T0 + 3))
        first, second = SensorLog.objects.order_by("timestamp")
        assert not AirQualityLog.objects.filter(sensor_log=first).exists()
        assert AirQualityLog.objects.filter(sensor_log=second).exists()


class TestConsumeOnce:

    def test_one_sample_attaches_to_one_row(self, live):
        feed(live, pm(t=T0), fix(t=T0), fix(t=T0 + 1))
        assert SensorLog.objects.count() == 2
        assert AirQualityLog.objects.count() == 1

    def test_newer_reading_replaces_unused_older(self, live):
        feed(live, rad(t=T0 - 0.5, cpm=10.0), rad(t=T0, cpm=99.0), fix(t=T0))
        assert RadiationLog.objects.get().radiation_value == 99.0


class TestProvenance:

    def test_mixed_row_live_fix_live_pm_simulated_radiation(self, live):
        """The Pass 5 row. Nothing reads SIM that's real; nothing reads LIVE that's sim."""
        feed(live, rad(source="simulated"), pm(source="live"), imu(source="live"), fix())
        log = SensorLog.objects.get()
        assert log.source == S.LIVE
        assert log.radiation_data.source == S.SIMULATED
        assert log.air_quality_data.source == S.LIVE
        assert log.imu_baro_data.source == S.LIVE

    def test_sim_ceiling_caps_a_live_claim(self, sim):
        feed(sim, pm(source="live"), fix())
        assert AirQualityLog.objects.get().source == S.SIMULATED

    @pytest.mark.parametrize("claim", [None, "", "LIVE", "reported", "modelled", "real"])
    def test_missing_or_unknown_claim_under_claims(self, live, claim):
        """Only 'live' earns LIVE. The robot can't claim REPORTED/MODELLED."""
        feed(live, pm(source=claim), fix())
        assert AirQualityLog.objects.get().source == S.SIMULATED

    def test_weakest_order(self):
        assert rd.weakest(S.LIVE, S.SIMULATED) == S.SIMULATED
        assert rd.weakest(S.LIVE, S.MODELLED) == S.MODELLED
        assert rd.weakest(S.REPORTED, S.LIVE) == S.REPORTED
        assert rd.weakest(S.LIVE, S.LIVE) == S.LIVE


class TestRejectOnArrival:

    def test_null_cpm_is_not_a_reading(self, live):
        feed(live, rad(cpm=None), fix())
        assert RadiationLog.objects.count() == 0
        assert live.counts["radiation_empty"] == 1

    def test_all_null_pm_is_not_a_reading(self, live):
        feed(live, pm(pm25=None, pm10=None), fix())
        assert AirQualityLog.objects.count() == 0

    def test_partial_imu_keeps_what_it_has(self, live):
        """NaN arrives as null: store null, don't drop the whole reading."""
        feed(live, imu(yaw=None, pressure_hpa=None, altitude_m=None), fix())
        i = ImuBaroLog.objects.get()
        assert (i.roll, i.yaw, i.pressure_baro) == (1.0, None, None)

    def test_no_stamp_is_rejected(self, live):
        key, msg = pm()
        del msg["header"]
        feed(live, (key, msg), fix())
        assert AirQualityLog.objects.count() == 0
        assert live.counts["air_quality_no_stamp"] == 1


class TestAtomic:

    def test_failed_reading_write_leaves_no_row(self, live, monkeypatch):
        def boom(**kw):
            raise RuntimeError("reading insert failed")
        monkeypatch.setattr(AirQualityLog.objects, "create", boom)
        feed(live, rad(), pm())
        with pytest.raises(RuntimeError):
            feed(live, fix())
        assert SensorLog.objects.count() == 0
        assert RadiationLog.objects.count() == 0
        assert live.counts["saved"] == 0


class TestInbox:

    def test_reading_callbacks_share_the_fix_inbox(self, live):
        """Callbacks only enqueue (ADR-0015); fixes and readings stay ordered."""
        import queue
        live.inbox = queue.Queue()
        live._enqueue("air_quality", pm()[1])
        live.on_fix(fix()[1])
        assert [live.inbox.get_nowait()[0] for _ in range(2)] == ["air_quality", "fix"]
        assert SensorLog.objects.count() == 0  # enqueue never writes
# ─── RANGER V3 END: 13-reading-assembly ───
