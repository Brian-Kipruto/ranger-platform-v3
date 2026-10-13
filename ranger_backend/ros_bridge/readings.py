# ─── RANGER V3 START: 13-reading-assembly ───
"""Reading topics → SensorLog readings: the contract and the assembly rule.

F13 5-pre, ADR-0020. No ORM and no rosbridge here, so the rule is testable in
isolation; ros_ingest owns the threads and the writes.

THE CONTRACT (ranger_msgs, robot side; rosbridge delivers these as JSON):

  /ranger/radiation   ranger_msgs/msg/Radiation  -> RadiationLog
      header, cpm, dose_rate_usvh, source
  /ranger/air_quality ranger_msgs/msg/AirQuality -> AirQualityLog
      header, pm25, pm10, source                     (µg/m³)
  /ranger/imu_baro    ranger_msgs/msg/ImuBaro    -> ImuBaroLog
      header, roll, pitch, yaw, pressure_hpa, altitude_m, source
      roll/pitch in degrees; yaw = compass heading, degrees clockwise from
      magnetic north, [0, 360). Missing values are NaN on the robot, which
      rosbridge sends as JSON null.

  `source` is the robot's CLAIM: "live" or "simulated". Anything else, or
  nothing, is treated as "simulated".

THE ASSEMBLY RULE (fork 8):
  * GPS-triggered. Only an accepted /fix writes a row; a reading on its own
    writes nothing (no positionless rows).
  * Latest value per topic. A newer reading replaces an unused older one.
  * Freshness in ROBOT time: a reading attaches iff
    |fix.stamp - reading.stamp| <= that topic's window. Never carried forward.
  * Consume-once: a reading attaches to at most one row. A 1 Hz fix with a 2 s
    window would otherwise put one PM sample on two rows, and duplicated
    samples bias every spatial analysis downstream.
  * Label = weakest(robot claim, operator ceiling). The ceiling is ros_ingest
    --source: in sim mode everything is SIMULATED whatever the robot says;
    in live mode a simulated Geiger still says SIMULATED.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from core.models import SensorLog

S = SensorLog.Source

# Most to least authoritative. weakest() picks the one furthest down.
STRENGTH = (S.LIVE, S.REPORTED, S.MODELLED, S.SIMULATED)
ROBOT_CLAIMS = {S.LIVE.value: S.LIVE, S.SIMULATED.value: S.SIMULATED}


def weakest(*sources):
    return max(sources, key=STRENGTH.index)


def stamp_to_datetime(msg):
    """header.stamp -> aware UTC datetime, or None if absent."""
    stamp = (msg.get("header") or {}).get("stamp") or {}
    if "sec" not in stamp:
        return None
    return datetime.fromtimestamp(
        stamp["sec"] + stamp.get("nanosec", 0) / 1e9, tz=timezone.utc
    )


def _num(v):
    """rosbridge sends NaN as null; a float NaN from any other path is the same."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


@dataclass(frozen=True)
class ReadingSpec:
    key: str             # also the attribute ros_ingest maps to a model
    topic: str
    msg_type: str
    fresh_s: float       # freshness window, robot time
    fields: tuple        # (msg_field, model_field) pairs
    required: str        # "any": at least one field; else the msg field that must be present
    throttle_ms: int = 0  # rosbridge-side throttle; 0 = every message


SPECS = (
    ReadingSpec(
        key="radiation", topic="/ranger/radiation",
        msg_type="ranger_msgs/msg/Radiation", fresh_s=2.0,
        fields=(("cpm", "radiation_value"), ("dose_rate_usvh", "dose_rate_usvh")),
        required="cpm",
    ),
    ReadingSpec(
        key="air_quality", topic="/ranger/air_quality",
        msg_type="ranger_msgs/msg/AirQuality", fresh_s=2.0,
        fields=(("pm25", "pm25"), ("pm10", "pm10")),
        required="any",
    ),
    ReadingSpec(
        key="imu_baro", topic="/ranger/imu_baro",
        msg_type="ranger_msgs/msg/ImuBaro", fresh_s=1.0,
        fields=(("roll", "roll"), ("pitch", "pitch"), ("yaw", "yaw"),
                ("pressure_hpa", "pressure_baro"), ("altitude_m", "altitude_baro")),
        required="any",
        throttle_ms=200,  # IMU publishes fast; only the latest is ever used
    ),
)
SPEC_BY_KEY = {s.key: s for s in SPECS}


@dataclass(frozen=True)
class Reading:
    key: str
    ts: datetime
    values: dict         # model_field -> float | None
    source: str          # effective label, already capped


class ReadingCache:
    """Latest unconsumed reading per topic. Main thread only — no lock."""

    def __init__(self, ceiling):
        self.ceiling = ceiling
        self.latest = {}

    def remember(self, key, msg):
        """Cache a reading. Returns None if kept, else the reason it wasn't."""
        spec = SPEC_BY_KEY[key]
        ts = stamp_to_datetime(msg)
        if ts is None:
            return "no_stamp"
        values = {model: _num(msg.get(field)) for field, model in spec.fields}
        present = [v for v in values.values() if v is not None]
        if spec.required == "any":
            if not present:
                return "empty"
        elif values[dict(spec.fields)[spec.required]] is None:
            return "empty"
        claim = ROBOT_CLAIMS.get(msg.get("source"), S.SIMULATED)
        self.latest[key] = Reading(key, ts, values, weakest(claim, self.ceiling))
        return None

    def take_fresh(self, fix_ts):
        """Pop every reading fresh for this fix. Returns (fresh, stale_keys).

        Fresh readings are consumed. Stale ones are dropped too: a reading too
        old for this fix is only older for the next one."""
        fresh, stale = [], []
        for key, r in list(self.latest.items()):
            if abs((fix_ts - r.ts).total_seconds()) <= SPEC_BY_KEY[key].fresh_s:
                fresh.append(self.latest.pop(key))
            elif r.ts < fix_ts:
                del self.latest[key]
                stale.append(key)
            # else: stamped beyond the window AFTER this fix — keep it for the
            # next fix (topics arrive out of order across rosbridge).
        return fresh, stale
# ─── RANGER V3 END: 13-reading-assembly ───
