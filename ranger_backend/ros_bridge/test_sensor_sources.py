# ─── RANGER V3 START: 13-sensor-sim ───
"""robot/sensor_sources.py on the PC: the Geiger seam, the sim models, and
their agreement with ranger_msgs and with ingest (F13 5-pre sim parity).

Loaded by path like nmea_sim (F11): it is robot code, deployed flat to
~/ranger/, with no rclpy at import.
"""
import importlib.util
import math
import random
import threading
import time
from collections import Counter

import pytest

from core.geo import KENYA_BBOX
from core.models import SensorLog
from ros_bridge.management.commands import ros_ingest as ingest
from ros_bridge.readings import ROBOT_CLAIMS
from ros_bridge.test_msg_contract import PKG, parse_msg


def _load(name, rel):
    path = PKG.parent / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load("sensor_sources", "sensor_sources.py")
nmea_sim = _load("nmea_sim", "tools/nmea_sim.py")
S = SensorLog.Source


class FakeNode:
    """Stands in for rclpy: captures the subscription the source makes."""

    def __init__(self):
        self.subs = {}

    def create_subscription(self, msg_type, topic, callback, qos):
        self.subs[topic] = (msg_type, callback)


class UInt32:
    def __init__(self, data):
        self.data = data


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def uno(stale_s=3.0):
    node, clock = FakeNode(), Clock()
    src = ss.UnoCounts(node, stale_s=stale_s, msg_type=UInt32, clock=clock)
    msg_type, report = node.subs[ss.GEIGER_COUNTS_TOPIC]
    assert msg_type is UInt32
    return src, report, clock


def make_source(name):
    if name == "uno":
        return uno()[0]
    return ss.COUNT_SOURCES[name](node=None, background_cpm=30.0)


def msg_fields(name):
    fields, consts = parse_msg(PKG / "msg" / f"{name}.msg")
    fields.pop("header")
    return set(fields), consts


class TestContract:

    def test_claim_constants_match_the_msgs(self):
        _, consts = msg_fields("Radiation")
        assert (ss.SOURCE_LIVE, ss.SOURCE_SIMULATED) == \
            (consts["SOURCE_LIVE"], consts["SOURCE_SIMULATED"])

    @pytest.mark.parametrize("name,fields", [
        ("Radiation", lambda: ss.radiation_fields(30.0, math.nan, ss.SOURCE_SIMULATED)),
        ("AirQuality", lambda: ss.SimAirQuality(rng=random.Random(1)).step()),
        ("ImuBaro", lambda: ss.SimImuBaro(1661.0, rng=random.Random(1)).step(0.1)),
    ])
    def test_node_fields_are_exactly_the_msg_fields(self, name, fields):
        """The nodes setattr() these keys onto the msg: a typo would raise on
        the Orin; a missing key would publish a silent default."""
        assert set(fields()) == msg_fields(name)[0]

    def test_sim_altitudes_match_nmea_sim(self):
        """Sim pressure must agree with the sim GPS's altitude at each site."""
        assert ss.SITE_ALTITUDE_M == {k: v[2] for k, v in nmea_sim.SITES.items()}


class TestGeigerSeam:

    @pytest.mark.parametrize("name", sorted(ss.COUNT_SOURCES))
    def test_every_source_has_the_seam_shape(self, name):
        src = make_source(name)
        assert src.claim in ROBOT_CLAIMS
        n = src.counts(1.0)
        assert n is None or isinstance(n, int)

    def test_the_two_sources_are_sim_and_uno(self):
        assert set(ss.COUNT_SOURCES) == {"sim", "uno"}

    def test_sim_source_claims_simulated(self):
        """Fork 7: the sim can't emit LIVE — the label travels with the source."""
        assert ss.COUNT_SOURCES["sim"].claim == ss.SOURCE_SIMULATED

    def test_poisson_mean_and_dispersion(self):
        """30 CPM -> 0.5 counts/s; Poisson means variance == mean."""
        src = ss.SimCounts(background_cpm=30.0, rng=random.Random(42))
        xs = [src.counts(1.0) for _ in range(20000)]
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / len(xs)
        assert mean == pytest.approx(0.5, abs=0.02)
        assert var / mean == pytest.approx(1.0, abs=0.05)

    def test_hotspot_adds_to_background(self):
        src = ss.SimCounts(background_cpm=30.0, rng=random.Random(7))
        src.hotspot_cpm = 570.0
        mean = sum(src.counts(1.0) for _ in range(5000)) / 5000
        assert mean == pytest.approx(10.0, rel=0.03)

    def test_large_rate_path(self):
        rng = random.Random(3)
        xs = [ss.poisson(rng, 1000.0) for _ in range(4000)]
        assert sum(xs) / len(xs) == pytest.approx(1000.0, rel=0.01)
        assert ss.poisson(rng, 0.0) == 0

    def test_sim_cpm_settles_on_background(self):
        src = ss.SimCounts(background_cpm=30.0, rng=random.Random(11))
        w = ss.CpmWindow(window_s=60.0)
        cpms = []
        for _ in range(3600):
            w.add(src.counts(1.0))
            cpms.append(w.cpm())
        settled = cpms[60:]
        assert sum(settled) / len(settled) == pytest.approx(30.0, rel=0.05)


class TestUnoSource:
    """The real tube's side of the seam, without a tube, an Uno or ROS."""

    def test_claims_live(self):
        assert ss.UnoCounts.claim == ss.SOURCE_LIVE

    def test_topic_is_the_bridge_contract(self):
        """The F14 uno_bridge publishes here; changing it breaks the swap silently."""
        assert ss.GEIGER_COUNTS_TOPIC == "/ranger/geiger_counts"

    def test_no_report_ever_is_no_data_not_zero(self):
        src, _, _ = uno()
        assert src.counts(1.0) is None

    def test_sums_reports_since_the_last_tick(self):
        src, report, clock = uno()
        for n in (3, 0, 2):
            report(UInt32(n))
            clock.t += 0.3
        assert src.counts(1.0) == 5
        report(UInt32(1))
        assert src.counts(1.0) == 1

    def test_live_feed_with_zero_counts_is_zero(self):
        """A working tube in a clean spot: 0 is a real reading."""
        src, report, _ = uno()
        report(UInt32(0))
        assert src.counts(1.0) == 0

    def test_stale_feed_is_no_data_and_drops_pending(self):
        src, report, clock = uno(stale_s=3.0)
        report(UInt32(7))
        clock.t += 3.01
        assert src.counts(1.0) is None
        report(UInt32(2))  # feed resumes
        assert src.counts(1.0) == 2  # the 7 from before the gap is gone

    def test_exactly_at_the_stale_limit_is_still_live(self):
        src, report, clock = uno(stale_s=3.0)
        report(UInt32(4))
        clock.t += 3.0
        assert src.counts(1.0) == 4


class TestRadiationTicker:

    def test_no_data_publishes_nothing_and_resets_the_window(self):
        src, report, clock = uno()
        t = ss.RadiationTicker(src, ss.CpmWindow(window_s=60.0))
        for _ in range(10):  # 10 s at 6 counts/s = 360 CPM
            report(UInt32(6))
            assert t.step(1.0)["cpm"] == pytest.approx(360.0)
            clock.t += 1.0
        clock.t += 5.0  # feed dies
        assert t.step(1.0) is None
        report(UInt32(1))  # back, at 60 CPM: no trace of the 360
        assert t.step(1.0)["cpm"] == pytest.approx(60.0)

    def test_sim_ticker_always_publishes(self):
        t = ss.RadiationTicker(ss.SimCounts(rng=random.Random(1)), ss.CpmWindow())
        assert all(t.step(1.0) is not None for _ in range(100))


class TestSwap:
    """5d: putting a real tube in = count_source:=uno. Same CPM maths, same
    fields, same topic and message; only the label changes."""

    def test_same_counts_same_cpm_different_label(self):
        counts = [0, 1, 0, 2, 1, 0, 0, 1, 3, 0]

        class Replay:  # a sim source fed fixed counts
            claim = ss.SOURCE_SIMULATED

            def __init__(self):
                self.it = iter(counts)

            def counts(self, dt_s):
                return next(self.it)

        src, report, _ = uno()
        sim_t = ss.RadiationTicker(Replay(), ss.CpmWindow())
        uno_t = ss.RadiationTicker(src, ss.CpmWindow())
        for n in counts:
            report(UInt32(n))
            a, b = sim_t.step(1.0), uno_t.step(1.0)
            assert set(a) == set(b) == msg_fields("Radiation")[0]
            assert a["cpm"] == b["cpm"]
            assert (a["source"], b["source"]) == (ss.SOURCE_SIMULATED, ss.SOURCE_LIVE)

    def test_stack_up_selects_the_source_by_one_parameter(self):
        """The swap is exactly this line in stack_up.sh (sim -> uno)."""
        stack = (PKG.parent / "tools" / "stack_up.sh").read_text()
        assert stack.count("radiation_node.py --ros-args -p count_source:=sim") == 1


class TestCpmWindow:

    def test_empty_is_nan(self):
        assert math.isnan(ss.CpmWindow().cpm())

    def test_partial_window_is_scaled_not_low(self):
        w = ss.CpmWindow(window_s=60.0)
        for c in (1, 0, 2):  # 3 counts in 3 s
            w.add(c)
        assert w.cpm() == pytest.approx(60.0)

    def test_full_window_rolls(self):
        w = ss.CpmWindow(window_s=60.0)
        for _ in range(60):
            w.add(1)
        assert w.cpm() == pytest.approx(60.0)
        for _ in range(60):
            w.add(0)
        assert w.cpm() == 0.0

    def test_window_shorter_than_tick_is_refused(self):
        with pytest.raises(ValueError):
            ss.CpmWindow(window_s=0.5, tick_s=1.0)


class TestDose:

    def test_no_factor_no_dose(self):
        assert math.isnan(ss.radiation_fields(30.0, math.nan, "simulated")["dose_rate_usvh"])

    def test_factor_gives_dose(self):
        assert ss.radiation_fields(30.0, 0.0057, "simulated")["dose_rate_usvh"] == \
            pytest.approx(0.171)

    def test_nan_cpm_gives_nan_dose(self):
        assert math.isnan(ss.radiation_fields(math.nan, 0.0057, "live")["dose_rate_usvh"])


class TestSimModels:

    def test_air_quality_is_plausible(self):
        aq = ss.SimAirQuality(pm25_mean=15.0, rng=random.Random(5))
        for _ in range(2000):
            r = aq.step()
            assert r["pm25"] >= 0.5
            assert r["pm10"] >= r["pm25"]
            assert r["source"] == ss.SOURCE_SIMULATED

    def test_yaw_stays_in_compass_range(self):
        imu = ss.SimImuBaro(1661.0, rng=random.Random(9))
        for _ in range(5000):
            yaw = imu.step(0.1)["yaw"]
            assert 0.0 <= yaw < 360.0

    def test_yaw_that_rounds_to_360_wraps_to_0(self):
        class NoNoise(random.Random):
            def gauss(self, mu=0.0, sigma=1.0):
                return 0.0
        imu = ss.SimImuBaro(1661.0, rng=NoNoise(0))
        imu.yaw = 359.996  # round(…, 2) == 360.0
        assert imu.step(0.0)["yaw"] == 0.0

    def test_pressure_matches_altitude(self):
        assert ss.pressure_hpa(0.0) == pytest.approx(1013.25)
        r = ss.SimImuBaro(1661.0, rng=random.Random(2)).step(0.1)
        assert r["pressure_hpa"] == pytest.approx(ss.pressure_hpa(r["altitude_m"]), abs=0.01)
        assert 820 < r["pressure_hpa"] < 840  # Nairobi


def _ingest_cmd(robot, monkeypatch, ceiling):
    monkeypatch.setattr(ingest, "close_old_connections", lambda: None)
    monkeypatch.setattr(ingest, "broadcast_sensorlog", lambda log: None)
    c = ingest.Command()
    c.robot, c.source, c.max_skew, c.note = robot, ceiling, 120.0, "test"
    c.region = KENYA_BBOX
    c.counts, c.lock, c.broadcast_up = Counter(), threading.Lock(), True
    c.readings = ingest.ReadingCache(ceiling=ceiling)
    return c


@pytest.mark.django_db
@pytest.mark.parametrize("ceiling,expected", [(S.LIVE, S.LIVE), (S.SIMULATED, S.SIMULATED)])
def test_real_tube_reading_through_real_ingest(robot, monkeypatch, ceiling, expected):
    """Live robot + uno source -> radiation stored LIVE. Sim mode (ceiling
    SIMULATED) still caps it: a real count on a fake position isn't ground truth."""
    c = _ingest_cmd(robot, monkeypatch, ceiling)
    src, report, _ = uno()
    t = ss.RadiationTicker(src, ss.CpmWindow())
    report(UInt32(2))
    fields = t.step(1.0)
    fields["dose_rate_usvh"] = None  # NaN over rosbridge
    hdr = {"stamp": {"sec": int(time.time()), "nanosec": 0}}
    c._dispatch(("radiation", {"header": hdr, **fields}))
    c._dispatch(("fix", {"header": hdr, "status": {"status": 0},
                         "latitude": -1.2864, "longitude": 36.8172}))
    log = SensorLog.objects.get()
    assert log.radiation_data.radiation_value == pytest.approx(120.0)
    assert log.radiation_data.source == expected


@pytest.mark.django_db
def test_sim_output_through_real_ingest_is_labelled_simulated(robot, monkeypatch):
    """End to end in Python: what the sim nodes publish, shaped as rosbridge
    JSON, through Command._dispatch with a LIVE ceiling. The fix is LIVE; every
    sim reading stays SIMULATED, because the claim travels with the source."""
    monkeypatch.setattr(ingest, "close_old_connections", lambda: None)
    monkeypatch.setattr(ingest, "broadcast_sensorlog", lambda log: None)
    c = ingest.Command()
    c.robot, c.source, c.max_skew, c.note = robot, S.LIVE, 120.0, "test"
    c.region = KENYA_BBOX
    c.counts, c.lock, c.broadcast_up = Counter(), threading.Lock(), True
    c.readings = ingest.ReadingCache(ceiling=S.LIVE)

    now = time.time()
    hdr = {"stamp": {"sec": int(now), "nanosec": 0}}
    rng = random.Random(4)
    window = ss.CpmWindow()
    src = ss.SimCounts(rng=rng)
    for _ in range(10):
        window.add(src.counts(1.0))
    rad = ss.radiation_fields(window.cpm(), math.nan, src.claim)
    rad["dose_rate_usvh"] = None  # rosbridge sends NaN as null
    for key, fields in (("radiation", rad),
                        ("air_quality", ss.SimAirQuality(rng=rng).step()),
                        ("imu_baro", ss.SimImuBaro(1661.0, rng=rng).step(0.1))):
        c._dispatch((key, {"header": hdr, **fields}))
    c._dispatch(("fix", {"header": hdr, "status": {"status": 0},
                         "latitude": -1.2864, "longitude": 36.8172}))

    log = SensorLog.objects.get()
    assert log.source == S.LIVE
    assert log.radiation_data.source == S.SIMULATED
    assert log.radiation_data.dose_rate_usvh is None
    assert log.air_quality_data.source == S.SIMULATED
    assert log.imu_baro_data.source == S.SIMULATED
    assert 0.0 <= log.imu_baro_data.yaw < 360.0
# ─── RANGER V3 END: 13-sensor-sim ───
