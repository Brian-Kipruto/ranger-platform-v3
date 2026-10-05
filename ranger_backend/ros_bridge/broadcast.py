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
    }


def broadcast_sensorlog(log) -> None:
    """Sync. Raises if the channel layer is down. The CALLER decides what a
    failure means (ros_ingest counts it and keeps writing rows)."""
    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        dashboard_group(log.robot.organization_id),
        {"type": "sensorlog.message", "payload": sensorlog_payload(log)},
    )
# ─── RANGER V3 END: 09-live-console ───
