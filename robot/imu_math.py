# ─── RANGER V3 START: 13-imu ───
"""Maths for imu_node: MPU6050 (0x68) + QMC5883L (0x0D) + BMP180 (0x77) on the
10-DOF board, I2C bus 7 (header pins 3/5). Pure Python, no smbus, no rclpy, so
the PC test suite loads it directly (F13).

FRAME: REP-103 body frame, FLU — x forward, y left, z up. The board can be
mounted any axis-aligned way: ~/ranger/config/imu_mount.json says which SENSOR
axis points forward and which points up (Mount), and both the accelerometer and
the magnetometer are rotated into FLU before any maths. No mount file -> the
node refuses to start: a guessed mount stores wrong roll/pitch as LIVE.
Assumes the QMC5883L's axes match the MPU6050's (checked at calibration).

HEADING is a compass heading: degrees clockwise from MAGNETIC north, [0, 360)
(the ranger_msgs/ImuBaro contract). Without a calibration it is computed for
the log only and published as NaN: an uncalibrated heading next to steel and
motors is confidently wrong, and must never be stored as LIVE.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

SOURCE_LIVE = "live"  # == ranger_msgs SOURCE_LIVE (asserted by test_imu_math)

MPU_ADDR, QMC_ADDR, BMP_ADDR = 0x68, 0x0D, 0x77
MPU_WHO_AM_I, BMP_CHIP_ID, QMC_CHIP_ID = 0x68, 0x55, 0xFF
ACCEL_LSB_PER_G = 16384.0  # ACCEL_CONFIG = 0x00, +-2 g


def s16be(hi, lo):
    v = (hi << 8) | lo
    return v - 0x10000 if v & 0x8000 else v


def s16le(lo, hi):
    return s16be(hi, lo)


def decode_accel_g(block):
    """MPU6050 ACCEL_XOUT_H.. (0x3B, >= 6 bytes, big-endian) -> (ax, ay, az) in g."""
    return tuple(s16be(block[i], block[i + 1]) / ACCEL_LSB_PER_G for i in (0, 2, 4))


def decode_mag(block):
    """QMC5883L 0x00..0x05 (little-endian X, Y, Z) -> raw counts."""
    return tuple(s16le(block[i], block[i + 1]) for i in (0, 2, 4))


# ── mount: sensor axes -> robot body (FLU) ──

AXES = {f"{sign}{axis}": (i, 1 if sign == "+" else -1)
        for i, axis in enumerate("xyz") for sign in "+-"}


def _unit(token):
    i, sign = AXES[token]
    v = [0, 0, 0]
    v[i] = sign
    return v


@dataclass(frozen=True)
class Mount:
    """Which sensor axis points along the robot's forward and up. Left follows
    (up x forward), so every Mount is a proper rotation — never a mirror."""
    forward: str
    up: str

    def __post_init__(self):
        for t in (self.forward, self.up):
            if t not in AXES:
                raise ValueError(f"mount axis {t!r} not one of {sorted(AXES)}")
        if self.forward[1] == self.up[1]:
            raise ValueError(f"forward {self.forward} and up {self.up} must be different axes")

    def rows(self):
        f, u = _unit(self.forward), _unit(self.up)
        left = [u[1] * f[2] - u[2] * f[1], u[2] * f[0] - u[0] * f[2], u[0] * f[1] - u[1] * f[0]]
        return f, left, u

    def apply(self, v):
        """Sensor-frame vector -> body FLU."""
        return tuple(sum(r[i] * v[i] for i in range(3)) for r in self.rows())


def load_mount(path):
    """-> Mount. Missing or malformed raises: no default mount exists."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: which sensor axes point forward/up? (F13 doc)")
    d = json.loads(p.read_text())
    return Mount(forward=d["forward"], up=d["up"])


def roll_pitch_deg(ax, ay, az):
    """Accelerometer specific force (flat = (0, 0, +1 g)) -> (roll, pitch), degrees.
    Static only: while driving, acceleration leaks in (a gyro filter is later work)."""
    roll = math.atan2(ay, az)
    pitch = math.atan2(-ax, math.hypot(ay, az))
    return math.degrees(roll), math.degrees(pitch)


def tilt_heading_deg(m, roll_deg, pitch_deg):
    """Calibrated mag vector (FLU) + roll/pitch -> compass heading [0, 360).

    De-rotates the field into the level plane, then measures the angle from
    body-forward to magnetic north, clockwise."""
    mx, my, mz = m
    phi, theta = math.radians(roll_deg), math.radians(pitch_deg)
    hx = mx * math.cos(theta) + (my * math.sin(phi) + mz * math.cos(phi)) * math.sin(theta)
    hy = my * math.cos(phi) - mz * math.sin(phi)
    heading = math.degrees(math.atan2(hy, hx)) % 360.0
    return 0.0 if heading >= 360.0 else heading  # -1e-15 % 360 == 360.0


def attitude(accel_s, mag_s, mount, cal=None, mag_overflow=False):
    """Sensor-frame accel + mag -> (roll, pitch, yaw, heading_raw), degrees.

    Order matters: calibration is a property of the chip's axes, so it applies
    in the SENSOR frame; only then is the field rotated into the body frame.
    yaw is NaN without a calibration (or on overflow); heading_raw is the
    uncalibrated value, for the log only."""
    roll, pitch = roll_pitch_deg(*mount.apply(accel_s))
    if mag_overflow:
        return roll, pitch, math.nan, math.nan
    heading_raw = tilt_heading_deg(mount.apply(mag_s), roll, pitch)
    yaw = tilt_heading_deg(mount.apply(cal.apply(mag_s)), roll, pitch) if cal else math.nan
    return roll, pitch, yaw, heading_raw


# ── magnetometer calibration (hard-iron offset + per-axis scale) ──

@dataclass(frozen=True)
class MagCal:
    offset: tuple
    scale: tuple

    def apply(self, m):
        return tuple((v - o) * s for v, o, s in zip(m, self.offset, self.scale))

    @classmethod
    def from_min_max(cls, lo, hi):
        """Per-axis min/max from a full rotation -> offset and scale."""
        half = [(h - lo_) / 2.0 for lo_, h in zip(lo, hi)]
        if min(half) <= 0:
            raise ValueError(f"degenerate range on an axis: min={lo} max={hi}")
        avg = sum(half) / 3.0
        return cls(offset=tuple((h + lo_) / 2.0 for lo_, h in zip(lo, hi)),
                   scale=tuple(avg / r for r in half))


def load_mag_cal(path):
    """-> MagCal, or None if the file doesn't exist (= not calibrated yet).
    A file that exists but is malformed raises: a broken calibration must
    stop the node, not silently fall back to 'uncalibrated' or worse."""
    p = Path(path).expanduser()
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    offset, scale = d["offset"], d["scale"]
    if len(offset) != 3 or len(scale) != 3 or not all(s > 0 for s in scale):
        raise ValueError(f"{p}: need 3 offsets and 3 positive scales, got {d}")
    return MagCal(tuple(map(float, offset)), tuple(map(float, scale)))


# ── BMP180 (datasheet rev 2.5, section 3.5) ──

@dataclass(frozen=True)
class Bmp180Cal:
    AC1: int
    AC2: int
    AC3: int
    AC4: int
    AC5: int
    AC6: int
    B1: int
    B2: int
    MB: int
    MC: int
    MD: int

    @classmethod
    def from_eeprom(cls, b):
        """22 bytes from 0xAA. AC4..AC6 unsigned, the rest signed; big-endian."""
        words = [(b[i] << 8) | b[i + 1] for i in range(0, 22, 2)]
        signed = [w - 0x10000 if (w & 0x8000 and k not in (3, 4, 5)) else w
                  for k, w in enumerate(words)]
        return cls(*signed)


def bmp180_temperature(ut, c):
    """-> (deg C, B5). Integer maths exactly as the datasheet."""
    x1 = ((ut - c.AC6) * c.AC5) >> 15
    x2 = (c.MC << 11) // (x1 + c.MD)
    b5 = x1 + x2
    return ((b5 + 8) >> 4) / 10.0, b5


def bmp180_pressure_pa(up, b5, c, oss):
    b6 = b5 - 4000
    x1 = (c.B2 * ((b6 * b6) >> 12)) >> 11
    x2 = (c.AC2 * b6) >> 11
    x3 = x1 + x2
    b3 = (((c.AC1 * 4 + x3) << oss) + 2) // 4
    x1 = (c.AC3 * b6) >> 13
    x2 = (c.B1 * ((b6 * b6) >> 12)) >> 16
    x3 = ((x1 + x2) + 2) >> 2
    b4 = (c.AC4 * (x3 + 32768)) >> 15
    b7 = (up - b3) * (50000 >> oss)
    p = (b7 * 2) // b4 if b7 < 0x80000000 else (b7 // b4) * 2
    x1 = (p >> 8) * (p >> 8)
    x1 = (x1 * 3038) >> 16
    x2 = (-7357 * p) >> 16
    return p + ((x1 + x2 + 3791) >> 4)


def altitude_m(pressure_pa, sea_level_pa=101325.0):
    """Barometric altitude, ICAO standard atmosphere (inverse of
    sensor_sources.pressure_hpa). Uncorrected for today's weather."""
    return 44330.0 * (1.0 - (pressure_pa / sea_level_pa) ** (1.0 / 5.255))


def imu_fields(roll, pitch, yaw, pressure_hpa, alt_m):
    """-> ranger_msgs/ImuBaro fields. Missing values are NaN."""
    return {"roll": float(roll), "pitch": float(pitch), "yaw": float(yaw),
            "pressure_hpa": float(pressure_hpa), "altitude_m": float(alt_m),
            "source": SOURCE_LIVE}
# ─── RANGER V3 END: 13-imu ───
