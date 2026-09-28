# ─── RANGER V3 START: 08-gps-ingest ───
"""
Subscribe to /fix on the robot via rosbridge; write one SensorLog per fix.

    python manage.py ros_ingest                  # source=simulated (default)
    python manage.py ros_ingest --source live    # ONLY with a real receiver under sky

Provenance: --source defaults to SIMULATED, the weakest tier a ROS feed can
carry. LIVE must be passed deliberately. A forgotten flag under-claims; it
never over-claims.

Skips (counted, never stored):
  no_fix        NavSatStatus < 0
  no_coords     lat/lon null — rosbridge sends NaN as JSON null
  clock_skew    robot stamp far from server time (unsynced Orin clock)
  out_of_region point_from_latlon's Kenya tripwire (catches lat/lon inversion)
"""
import math
import threading
import time
from collections import Counter
from datetime import datetime, timezone as dt_tz
import math
import queue
import roslibpy
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from core.geo import point_from_latlon
from core.models import Robot, SensorLog

ROS_SOURCES = (SensorLog.Source.SIMULATED, SensorLog.Source.LIVE)


class Command(BaseCommand):
    help = "Ingest sensor_msgs/NavSatFix from the robot (rosbridge) into SensorLog rows."

    def add_arguments(self, parser):
        parser.add_argument("--robot", default="RANGER-PRIME-001")
        parser.add_argument(
            "--source",
            choices=[s.value for s in ROS_SOURCES],
            default=SensorLog.Source.SIMULATED.value,
        )
        parser.add_argument("--host", default="192.168.55.1")
        parser.add_argument("--port", type=int, default=9090)
        parser.add_argument("--topic", default="/fix")
        parser.add_argument(
            "--max-skew", type=float, default=120.0,
            help="Reject fixes whose robot stamp differs from server time by more than N seconds.",
        )

    def handle(self, *args, **opts):
        try:
            robot = Robot.objects.get(robot_id_str=opts["robot"])
        except Robot.DoesNotExist:
            raise CommandError(f"No robot with robot_id_str={opts['robot']!r}")

        self.robot = robot
        self.source = opts["source"]
        self.max_skew = opts["max_skew"]
        self.note = f"ros_bridge {opts['topic']} via rosbridge {opts['host']}:{opts['port']}"
        self.counts = Counter()
        self.lock = threading.Lock()
        self.inbox = queue.Queue(maxsize=1000)

        client = roslibpy.Ros(host=opts["host"], port=opts["port"])
        try:
            client.run(timeout=10)
        except Exception as exc:
            raise CommandError(f"Cannot reach rosbridge at {opts['host']}:{opts['port']}: {exc}")

        topic = roslibpy.Topic(client, opts["topic"], "sensor_msgs/msg/NavSatFix")
        topic.subscribe(self.on_fix)
        self.stdout.write(
            f"Connected. {opts['topic']} -> SensorLog for {robot.robot_id_str} "
            f"(source={self.source}). Ctrl-C to stop."
        )

        connected = True
        try:
            while True:
                try:
                    m = self.inbox.get(timeout=1)
                except queue.Empty:
                    m = None
                if m is not None:
                    try:
                        self._ingest(m)
                    except Exception as exc:
                        self._count("error")
                        self.stderr.write(f"ingest error: {exc!r}")
                if client.is_connected != connected:
                    connected = client.is_connected
                    self.stderr.write(f"rosbridge {'reconnected' if connected else 'DISCONNECTED'}")
            pass
        finally:
            topic.unsubscribe()
            client.terminate()
            self.stdout.write(f"Stopped. {dict(self.counts)}")

    def _count(self, key):
        with self.lock:
            self.counts[key] += 1

    def on_fix(self, m):
        # Runs on roslibpy's Twisted reactor thread, which has an event loop:
        # Django raises SynchronousOnlyOperation for ORM calls there. Enqueue
        # only; the main (sync) thread does the DB writes.
        try:
            self.inbox.put_nowait(m)
        except queue.Full:
            self._count("dropped")

    def _ingest(self, m):
        status = (m.get("status") or {}).get("status", -1)
        if status < 0:
            return self._count("no_fix")

        lat, lon = m.get("latitude"), m.get("longitude")
        if lat is None or lon is None or math.isnan(lat) or math.isnan(lon):
            return self._count("no_coords")

        stamp = (m.get("header") or {}).get("stamp") or {}
        ts = datetime.fromtimestamp(
            stamp.get("sec", 0) + stamp.get("nanosec", 0) / 1e9, tz=dt_tz.utc
        )
        skew = abs((timezone.now() - ts).total_seconds())
        if skew > self.max_skew:
            self.stderr.write(f"skip: robot clock skew {skew:.0f}s — is the Orin clock synced?")
            return self._count("clock_skew")

        try:
            point = point_from_latlon(lat=lat, lon=lon)
        except ValueError as exc:
            self.stderr.write(f"skip: {exc}")
            return self._count("out_of_region")

        close_old_connections()
        log = SensorLog.objects.create(
            robot=self.robot,
            timestamp=ts,
            location=point,
            source=self.source,
            provenance_note=self.note,
        )
        self._count("saved")
        self.stdout.write(f"SensorLog #{log.pk}: {lat:.6f}, {lon:.6f} [{self.source}] @ {ts:%H:%M:%S}Z")
# ─── RANGER V3 END: 08-gps-ingest ───