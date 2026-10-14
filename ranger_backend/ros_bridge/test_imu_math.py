# ─── RANGER V3 START: 13-imu ───
"""robot/imu_math.py on the PC (F13 5c): the maths imu_node runs on the Orin.

The heading tests build the sensor readings from a known attitude with
rotation matrices (REP-103 FLU body, world = North/West/Up) and require the
formulas to recover it. That proves the maths is self-consistent; whether the
board's physical axes match FLU is checked at calibration, on the robot.
"""
import importlib.util
import json
import math
import random
import struct

import pytest

from ros_bridge.test_msg_contract import PKG, parse_msg


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, PKG.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


im = _load("imu_math", "imu_math.py")
ss = _load("sensor_sources", "sensor_sources.py")

# BMP180 datasheet rev 2.5, section 3.5 worked example.
DS_CAL = dict(AC1=408, AC2=-72, AC3=-14383, AC4=32741, AC5=32757, AC6=23153,
              B1=6190, B2=4, MB=-32768, MC=-8711, MD=2868)


def rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
            "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def body(world_vec, heading, roll, pitch):
    """World (N, W, U) vector -> body FLU, for a compass heading (clockwise from N)."""
    r = mul(mul(rot("z", -heading), rot("y", pitch)), rot("x", roll))  # body -> world
    return tuple(sum(r[k][i] * world_vec[k] for k in range(3)) for i in range(3))  # R^T v


FIELD = (0.30, 0.0, -0.20)  # north and down (any dip works)
GRAVITY_SF = (0.0, 0.0, 1.0)  # specific force at rest: up


class TestBmp180:

    def test_datasheet_example(self):
        c = im.Bmp180Cal(**DS_CAL)
        t, b5 = im.bmp180_temperature(27898, c)
        assert (t, b5) == (15.0, 2399)
        assert im.bmp180_pressure_pa(23843, b5, c, 0) == 69964

    def test_eeprom_signedness(self):
        """AC4-AC6 are unsigned; everything else is signed (MB = -32768)."""
        raw = struct.pack(">hhhHHHhhhhh", *DS_CAL.values())
        assert im.Bmp180Cal.from_eeprom(list(raw)) == im.Bmp180Cal(**DS_CAL)

    def test_high_unsigned_words_stay_positive(self):
        """The datasheet's AC4-AC6 are all < 0x8000, so it can't catch a signed
        read of them. Real chips often have AC4 > 32767."""
        vals = dict(DS_CAL, AC4=40000, AC5=33000, AC6=50000)
        raw = struct.pack(">hhhHHHhhhhh", *vals.values())
        cal = im.Bmp180Cal.from_eeprom(list(raw))
        assert (cal.AC4, cal.AC5, cal.AC6) == (40000, 33000, 50000)

    def test_altitude_inverts_the_sim_pressure(self):
        for alt in (0.0, 75.0, 1661.0, 3000.0):
            pa = ss.pressure_hpa(alt) * 100.0
            assert im.altitude_m(pa) == pytest.approx(alt, abs=0.5)


class TestDecode:

    def test_big_endian_signed_accel(self):
        block = [0x40, 0x00, 0xC0, 0x00, 0x00, 0x00]  # +16384, -16384, 0
        assert im.decode_accel_g(block) == (1.0, -1.0, 0.0)

    def test_little_endian_signed_mag(self):
        assert im.decode_mag([0x01, 0x00, 0xFF, 0xFF, 0x00, 0x80]) == (1, -1, -32768)


class TestAttitude:

    def test_flat_is_level(self):
        assert im.roll_pitch_deg(0.0, 0.0, 1.0) == (0.0, 0.0)

    @pytest.mark.parametrize("roll,pitch", [(10, 0), (0, 15), (-20, 30), (35, -25)])
    def test_roll_pitch_recovered(self, roll, pitch):
        f = body(GRAVITY_SF, 0.0, roll, pitch)
        assert im.roll_pitch_deg(*f) == pytest.approx((roll, pitch), abs=1e-9)

    @pytest.mark.parametrize("heading", [0, 45, 90, 135, 180, 225, 270, 315])
    def test_level_heading_is_clockwise_from_north(self, heading):
        m = body(FIELD, heading, 0.0, 0.0)
        assert im.tilt_heading_deg(m, 0.0, 0.0) == pytest.approx(heading, abs=1e-9)

    def test_tilt_compensation_recovers_heading(self):
        """Random attitudes: tilting the robot must not move the heading."""
        rng = random.Random(13)
        for _ in range(500):
            h, r, p = rng.uniform(0, 360), rng.uniform(-40, 40), rng.uniform(-40, 40)
            f = body(GRAVITY_SF, h, r, p)
            roll, pitch = im.roll_pitch_deg(*f)
            got = im.tilt_heading_deg(body(FIELD, h, r, p), roll, pitch)
            assert min(abs(got - h), 360 - abs(got - h)) < 1e-6, (h, r, p, got)

    def test_heading_range(self):
        assert 0.0 <= im.tilt_heading_deg((1.0, -1e-17, 0.0), 0.0, 0.0) < 360.0


class TestMagCal:

    def test_from_min_max_centres_and_equalises(self):
        cal = im.MagCal.from_min_max(lo=(-100, -50, -300), hi=(300, 150, -100))
        assert cal.offset == (100.0, 50.0, -200.0)
        scaled = [cal.apply(v) for v in [(300, 50, -200), (100, 150, -200), (100, 50, -100)]]
        assert [max(abs(x) for x in v) for v in scaled] == pytest.approx([400 / 3 * 1.0] * 3)

    def test_calibration_undoes_hard_iron(self):
        """A fixed bias wrecks raw heading; the offset removes it."""
        bias = (120.0, -80.0, 40.0)
        true = body(FIELD, 90.0, 0.0, 0.0)
        raw = tuple(t * 1000 + b for t, b in zip(true, bias))
        cal = im.MagCal(offset=bias, scale=(1.0, 1.0, 1.0))
        assert abs(im.tilt_heading_deg(raw, 0, 0) - 90.0) > 20  # visibly wrong raw
        assert im.tilt_heading_deg(cal.apply(raw), 0, 0) == pytest.approx(90.0, abs=1e-9)

    def test_degenerate_range_refused(self):
        with pytest.raises(ValueError):
            im.MagCal.from_min_max(lo=(0, 0, 5), hi=(10, 10, 5))

    def test_missing_file_means_uncalibrated(self, tmp_path):
        assert im.load_mag_cal(tmp_path / "nope.json") is None

    def test_good_file_loads(self, tmp_path):
        p = tmp_path / "mag_cal.json"
        p.write_text(json.dumps({"offset": [1, 2, 3], "scale": [1.0, 0.9, 1.1]}))
        assert im.load_mag_cal(p) == im.MagCal((1.0, 2.0, 3.0), (1.0, 0.9, 1.1))

    @pytest.mark.parametrize("bad", [
        {"offset": [1, 2], "scale": [1, 1, 1]},
        {"offset": [1, 2, 3], "scale": [1, 0, 1]},
        {"scale": [1, 1, 1]},
    ])
    def test_malformed_file_stops_the_node(self, tmp_path, bad):
        p = tmp_path / "mag_cal.json"
        p.write_text(json.dumps(bad))
        with pytest.raises((ValueError, KeyError)):
            im.load_mag_cal(p)


ALL_MOUNTS = [im.Mount(f, u) for f in im.AXES for u in im.AXES if f[1] != u[1]]
SHIPPED_MOUNT = PKG.parent / "config" / "imu_mount.json"


def to_sensor(mount, body_vec):
    """Inverse of Mount.apply (rows are orthonormal): s = R^T b."""
    rows = mount.rows()
    return tuple(sum(rows[k][i] * body_vec[k] for k in range(3)) for i in range(3))


class TestMount:

    def test_there_are_24_and_all_are_proper_rotations(self):
        assert len(ALL_MOUNTS) == 24
        for m in ALL_MOUNTS:
            f, lf, u = m.rows()
            det = (f[0] * (lf[1] * u[2] - lf[2] * u[1]) - f[1] * (lf[0] * u[2] - lf[2] * u[0])
                   + f[2] * (lf[0] * u[1] - lf[1] * u[0]))
            assert det == 1, m  # a mirror (-1) would flip heading direction

    @pytest.mark.parametrize("mount", ALL_MOUNTS, ids=lambda m: f"fwd{m.forward}_up{m.up}")
    def test_any_mount_recovers_attitude(self, mount):
        rng = random.Random(hash((mount.forward, mount.up)) & 0xFFFF)
        for _ in range(40):
            h, r, p = rng.uniform(0, 360), rng.uniform(-35, 35), rng.uniform(-35, 35)
            accel_s = to_sensor(mount, body(GRAVITY_SF, h, r, p))
            mag_s = to_sensor(mount, body(FIELD, h, r, p))
            cal = im.MagCal((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
            roll, pitch, yaw, raw = im.attitude(accel_s, mag_s, mount, cal)
            assert (roll, pitch) == pytest.approx((r, p), abs=1e-6)
            assert min(abs(yaw - h), 360 - abs(yaw - h)) < 1e-6
            # identity calibration: the log's raw heading is the same number
            assert min(abs(raw - h), 360 - abs(raw - h)) < 1e-6

    def test_shipped_mount_is_the_6wd_board(self):
        """Vertical on an extrusion, pins up, chip side to the back (2026-10-13)."""
        assert im.load_mount(SHIPPED_MOUNT) == im.Mount(forward="-z", up="-x")

    def test_shipped_mount_explains_the_bench_reading(self):
        """The first bench run read roll -166 / pitch +80 under the flat-board
        assumption: accel (-0.98, -0.04, -0.17) g. With the real mount that is
        the robot nearly level, ~10 deg nose-up (the bracket's lean)."""
        mount = im.load_mount(SHIPPED_MOUNT)
        roll, pitch, _, _ = im.attitude((-0.98, -0.04, -0.17), (1, 0, 0), mount)
        assert roll == pytest.approx(2.3, abs=0.1)
        assert pitch == pytest.approx(-9.8, abs=0.1)

    @pytest.mark.parametrize("forward,up", [("+x", "-x"), ("+z", "+z"), ("x", "+y"), ("+w", "+z")])
    def test_invalid_mounts_refused(self, forward, up):
        with pytest.raises(ValueError):
            im.Mount(forward, up)

    def test_missing_mount_file_refuses(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            im.load_mount(tmp_path / "imu_mount.json")

    def test_mount_file_without_up_refuses(self, tmp_path):
        p = tmp_path / "imu_mount.json"
        p.write_text(json.dumps({"forward": "-z"}))
        with pytest.raises(KeyError):
            im.load_mount(p)


class TestAttitudeComposition:
    MOUNT = im.Mount(forward="-z", up="-x")

    def test_calibration_applies_in_the_sensor_frame(self):
        """Hard iron is a bias on the CHIP's axes. Calibrate, then rotate."""
        bias_s = (250.0, -400.0, 120.0)
        h = 135.0
        mag_s = tuple(1000 * v + b for v, b in
                      zip(to_sensor(self.MOUNT, body(FIELD, h, 0, 0)), bias_s))
        accel_s = to_sensor(self.MOUNT, body(GRAVITY_SF, h, 0, 0))
        cal = im.MagCal(offset=bias_s, scale=(1.0, 1.0, 1.0))
        _, _, yaw, raw = im.attitude(accel_s, mag_s, self.MOUNT, cal)
        assert yaw == pytest.approx(h, abs=1e-9)
        assert abs(raw - h) > 10  # the uncalibrated value really is wrong

    def test_no_calibration_means_nan_yaw_but_a_raw_heading(self):
        _, _, yaw, raw = im.attitude((-1, 0, 0), (0, 0, -300), self.MOUNT, None)
        assert math.isnan(yaw) and math.isfinite(raw)

    def test_overflow_means_no_heading_at_all(self):
        cal = im.MagCal((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        roll, pitch, yaw, raw = im.attitude((-1, 0, 0), (0, 0, -300), self.MOUNT, cal,
                                            mag_overflow=True)
        assert math.isnan(yaw) and math.isnan(raw)
        assert math.isfinite(roll) and math.isfinite(pitch)


class TestContract:

    def test_fields_are_exactly_the_msg_fields(self):
        fields, consts = parse_msg(PKG / "msg" / "ImuBaro.msg")
        fields.pop("header")
        assert set(im.imu_fields(0, 0, math.nan, 830.0, 1661.0)) == set(fields)
        assert im.SOURCE_LIVE == consts["SOURCE_LIVE"]

    def test_uncalibrated_yaw_is_nan_not_a_number(self):
        """The node passes NaN when uncalibrated; it must survive as NaN
        (rosbridge -> null -> stored null), never become 0.0."""
        assert math.isnan(im.imu_fields(1, 2, math.nan, 830, 1661)["yaw"])
# ─── RANGER V3 END: 13-imu ───
