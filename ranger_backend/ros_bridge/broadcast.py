# ─── RANGER V3 START: 09-live-console ───
"""
Live fan-out of saved rows to the Dashboard (F09).

One group per organization. The sender (ros_ingest) and the receiver
(DashboardConsumer) both name the group through dashboard_group(), so they
cannot drift apart.

Channels group names must match ^[a-zA-Z0-9\\-_.]+$ and be < 100 chars.
Colons are rejected, so the vault's `dashboard:<org>` is invalid.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ObjectDoesNotExist


def dashboard_group(org_id: int) -> str:
    return f"dashboard.org.{org_id}"


def sensorlog_payload(log) -> dict:
    """Built from the SAVED row, never the raw ROS message: the console shows
    exactly what the database holds."""
    return {
        "type": "sensorlog",
        "id": log.pk,
        "robot": log.robot.robot_id_str,
        "ts": log.timestamp.isoformat().replace("+00:00", "Z"),
        "lat": log.latitude,
        "lon": log.longitude,
        "source": log.source,
        "readings": readings_payload(log),  # 13-console-readings
    }


# ─── RANGER V3 START: 13-console-readings ───
def _reading(log, attr):
    try:
        return getattr(log, attr)
    except ObjectDoesNotExist:
        return None


def readings_payload(log) -> dict:
    """The readings saved on this row, each with ITS OWN source (ADR-0020).

    The row's `source` above is the position's. A live robot with a simulated
    tube sends source=live and readings.radiation.source=simulated, and the
    console must show both. Absent readings are absent keys — never a zero,
    never a carried-forward value. NaN never appears: the DB stores null."""
    out = {}
    r = _reading(log, "radiation_data")
    if r is not None:
        out["radiation"] = {"cpm": r.radiation_value, "dose_rate_usvh": r.dose_rate_usvh,
                            "source": r.source}
    a = _reading(log, "air_quality_data")
    if a is not None:
        out["air_quality"] = {"pm25": a.pm25, "pm10": a.pm10, "source": a.source}
    i = _reading(log, "imu_baro_data")
    if i is not None:
        out["imu_baro"] = {"roll": i.roll, "pitch": i.pitch, "yaw": i.yaw,
                           "pressure_hpa": i.pressure_baro, "altitude_m": i.altitude_baro,
                           "source": i.source}
    return out
# ─── RANGER V3 END: 13-console-readings ───


def broadcast_sensorlog(log) -> None:
    """Sync. Raises if the channel layer is down. The CALLER decides what a
    failure means (ros_ingest counts it and keeps writing rows)."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        dashboard_group(log.robot.organization_id),
        {"type": "sensorlog.message", "payload": sensorlog_payload(log)},
    )
# ─── RANGER V3 END: 09-live-console ───
