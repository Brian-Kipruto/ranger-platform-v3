# ─── RANGER V3 START: 13-sensor-sim ───
"""Sensor logic for the robot nodes. Pure Python: no rclpy, no serial at import,
so the PC test suite loads it directly (like nmea_sim, F11).

THE GEIGER SEAM (F13; the deliverable is the seam, not the sim)
  radiation_node asks a COUNT SOURCE for counts each tick, windows them into
  CPM (CpmWindow) and publishes ranger_msgs/Radiation with the source's CLAIM.
  A count source is any object with:
      claim              "live" | "simulated" — travels with the source, so
                         swapping the source swaps the label; nobody has to
                         remember to flip a flag
      counts(dt_s)       counts since the last call, or None = NO DATA (the
                         feed is dead/stale). None is not 0: a dead tube must
                         never read as a clean area labelled LIVE.
  COUNT_SOURCES maps the node's `count_source` parameter to a class:
      sim  SimCounts   Poisson, claims SIMULATED (today: the tube is dead)
      uno  UnoCounts   real tube via the Uno, claims LIVE (5d)
  Swapping the tube in is `-p count_source:=uno` in stack_up.sh. Nothing else.

  The Uno counts, it does not compute CPM: it sends `G,<counts>` (counts since
  its previous G line, about once a second) and the bridge that owns the Uno's
  serial port (F14 — it also carries motor commands) republishes each as
  std_msgs/UInt32 on /ranger/geiger_counts. Windowing happens once, here, the
  same way for sim and real counts.

SIM MODELS for sim mode (stand-ins for the SDS011 and MPU6050 until 5c's real
nodes). Each step() returns a dict whose keys are exactly the ranger_msgs
fields (test_sensor_sources asserts it against the .msg files).
"""
import math
import random
import time
from collections import deque

# == ranger_msgs SOURCE_* constants (asserted by test_sensor_sources).
SOURCE_LIVE = "live"
SOURCE_SIMULATED = "simulated"


def poisson(rng, lam):
    """One Poisson draw. Knuth for small lam; normal approximation above 500,
    where Knuth's exp(-lam) underflows and the two are indistinguishable."""
    if lam <= 0:
        return 0
    if lam > 500:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class SimCounts:
    """A simulated GM tube: Poisson counts at (background + hotspot) CPM.

    `hotspot_cpm` is the operator's demo lever (fork 4): radiation_node maps
    its parameter onto it at runtime. Always claims SIMULATED.
    """

    claim = SOURCE_SIMULATED

    def __init__(self, node=None, background_cpm=30.0, rng=None):
        self.background_cpm = float(background_cpm)
        self.hotspot_cpm = 0.0
        self.rng = rng or random.Random()

    def counts(self, dt_s):
        rate_cpm = self.background_cpm + self.hotspot_cpm
        return poisson(self.rng, rate_cpm * dt_s / 60.0)


GEIGER_COUNTS_TOPIC = "/ranger/geiger_counts"


class UnoCounts:
    """The real GM tube, via the Uno (5d seam; live once a tube works).

    Subscribes to /ranger/geiger_counts (std_msgs/UInt32, counts per report)
    and hands radiation_node the sum since its last tick. No report for
    `stale_s` -> None (no data), never 0. Claims LIVE.

    `msg_type` and `clock` are injectable so the PC tests run without ROS.
    """

    claim = SOURCE_LIVE

    def __init__(self, node, background_cpm=None, stale_s=3.0, msg_type=None,
                 clock=time.monotonic):
        if msg_type is None:
            from std_msgs.msg import UInt32 as msg_type  # robot only
        self.stale_s = float(stale_s)
        self.clock = clock
        self.pending = 0
        self.last_report = None
        node.create_subscription(msg_type, GEIGER_COUNTS_TOPIC, self.on_report, 10)

    def on_report(self, msg):
        self.pending += int(msg.data)
        self.last_report = self.clock()

    def counts(self, dt_s):
        if self.last_report is None or self.clock() - self.last_report > self.stale_s:
            self.pending = 0
            return None
        n, self.pending = self.pending, 0
        return n


# count_source parameter -> class.
COUNT_SOURCES = {"sim": SimCounts, "uno": UnoCounts}


class RadiationTicker:
    """One radiation_node tick: source -> window -> Radiation fields, or None.

    No data from the source -> the window is cleared (stale counts must not
    leak into the next CPM) and nothing is published, so ingest attaches no
    radiation rather than a stale or zero value."""

    def __init__(self, source, window, usvh_per_cpm=math.nan):
        self.source, self.window, self.usvh_per_cpm = source, window, usvh_per_cpm

    def step(self, dt_s):
        n = self.source.counts(dt_s)
        if n is None:
            self.window.ticks.clear()
            return None
        self.window.add(n)
        return radiation_fields(self.window.cpm(), self.usvh_per_cpm, self.source.claim)


class CpmWindow:
    """Rolling counts -> CPM, the way a Geiger counter display does it.

    Until the window fills, CPM is scaled from the ticks seen so far rather
    than reported low. Empty -> NaN (rosbridge sends null; ingest drops it).
    """

    def __init__(self, window_s=60.0, tick_s=1.0):
        if window_s < tick_s:
            raise ValueError("window_s must be >= tick_s")
        self.tick_s = float(tick_s)
        self.ticks = deque(maxlen=int(round(window_s / tick_s)))

    def add(self, counts):
        self.ticks.append(int(counts))

    def cpm(self):
        if not self.ticks:
            return math.nan
        return sum(self.ticks) * 60.0 / (len(self.ticks) * self.tick_s)


def radiation_fields(cpm, usvh_per_cpm, claim):
    """-> ranger_msgs/Radiation fields. Dose is NaN unless a tube conversion
    factor is configured: a dose from an unknown tube is false precision."""
    dose = cpm * usvh_per_cpm if math.isfinite(usvh_per_cpm) and math.isfinite(cpm) else math.nan
    return {"cpm": float(cpm), "dose_rate_usvh": float(dose), "source": claim}


# Site altitudes for the barometer sim. MUST equal nmea_sim.SITES altitudes
# (asserted by test_sensor_sources), or sim pressure and sim GPS disagree.
SITE_ALTITUDE_M = {"nairobi": 1661.0, "rabat": 75.0}


def pressure_hpa(altitude_m):
    """ICAO standard atmosphere, troposphere."""
    return 1013.25 * (1.0 - 2.25577e-5 * altitude_m) ** 5.25588


class SimAirQuality:
    """SDS011 stand-in: mean-reverting PM2.5 walk, PM10 1.5-2x PM2.5,
    0.1 ug/m3 resolution like the real sensor. Always claims SIMULATED."""

    claim = SOURCE_SIMULATED

    def __init__(self, pm25_mean=15.0, rng=None):
        self.mean = float(pm25_mean)
        self.pm25 = self.mean
        self.rng = rng or random.Random()

    def step(self):
        self.pm25 += 0.1 * (self.mean - self.pm25) + self.rng.gauss(0.0, 1.0)
        self.pm25 = max(0.5, self.pm25)
        pm10 = self.pm25 * self.rng.uniform(1.5, 2.0)
        return {"pm25": round(self.pm25, 1), "pm10": round(pm10, 1), "source": self.claim}


class SimImuBaro:
    """MPU6050 + QMC5883L + BMP180 stand-in. Yaw is a compass heading,
    degrees clockwise from magnetic north, [0, 360). Always claims SIMULATED."""

    claim = SOURCE_SIMULATED

    def __init__(self, altitude_m, rng=None):
        self.altitude_m = float(altitude_m)
        self.rng = rng or random.Random()
        self.yaw = self.rng.uniform(0.0, 360.0)

    def step(self, dt_s):
        g = self.rng.gauss
        self.yaw = (self.yaw + 3.0 * dt_s + g(0.0, 0.2)) % 360.0  # slow turn
        alt = self.altitude_m + g(0.0, 0.3)
        return {
            "roll": round(g(0.0, 1.5), 2),
            "pitch": round(g(0.0, 1.5), 2),
            "yaw": round(self.yaw, 2) % 360.0,  # 359.996 rounds to 360.0
            "pressure_hpa": round(pressure_hpa(alt), 2),
            "altitude_m": round(alt, 2),
            "source": self.claim,
        }
# ─── RANGER V3 END: 13-sensor-sim ───
