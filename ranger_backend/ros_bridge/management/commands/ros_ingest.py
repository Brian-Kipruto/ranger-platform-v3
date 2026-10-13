# ─── RANGER V3 START: 08-gps-ingest ───
"""
Subscribe to /fix on the robot via rosbridge; write one SensorLog per fix.

    python manage.py ros_ingest                  # source=simulated (default)
    python manage.py ros_ingest --source live    # ONLY with a real receiver under sky
    python manage.py ros_ingest --region rabat   # F11: guard box other than Kenya

Provenance: --source defaults to SIMULATED, the weakest tier a ROS feed can
carry. LIVE must be passed deliberately. A forgotten flag under-claims; it
never over-claims.

Skips (counted, never stored):
  no_fix        NavSatStatus < 0
  no_coords     lat/lon null — rosbridge sends NaN as JSON null
  clock_skew    robot stamp far from server time (unsynced Orin clock)
  out_of_region point_from_latlon's region tripwire (catches lat/lon inversion);
                --region picks the box, default kenya, "none" disables it (loudly)

F13 readings (ros_bridge/readings.py, ADR-0020): radiation, air quality and
IMU/baro topics are cached and attached to the next accepted fix if fresh in
robot time, each at most once, labelled weakest(robot claim, --source). The
row and its readings are one transaction. Counted, never stored:
  <key>_attached / <key>_stale    per fix
  <key>_no_stamp / <key>_empty    rejected on arrival
"""
import math
import threading
import time
from collections import Counter
from datetime import datetime, timezone as dt_tz
import queue
import roslibpy
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, transaction
from django.utils import timezone

from core.geo import point_from_latlon
# ─── RANGER V3 START: 11-ingest-region ───
from core.geo import REGION_CHOICES, REGION_NONE, resolve_region
# ─── RANGER V3 END: 11-ingest-region ───
from core.models import AirQualityLog, ImuBaroLog, RadiationLog, Robot, SensorLog
# ─── RANGER V3 START: 09-live-console ───
from ros_bridge.broadcast import broadcast_sensorlog
# ─── RANGER V3 END: 09-live-console ───
# ─── RANGER V3 START: 13-reading-assembly ───
from ros_bridge.readings import SPECS, ReadingCache, stamp_to_datetime

READING_MODELS = {
    "radiation": RadiationLog,
    "air_quality": AirQualityLog,
    "imu_baro": ImuBaroLog,
}
FIX = "fix"
# ─── RANGER V3 END: 13-reading-assembly ───

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
        # ─── RANGER V3 START: 11-ingest-region ───
        parser.add_argument(
            "--region", choices=REGION_CHOICES, default="kenya",
            help="Sanity box every fix must fall inside (inversion tripwire). "
                 "'none' disables it — escape hatch only.",
        )
        # ─── RANGER V3 END: 11-ingest-region ───

    def handle(self, *args, **opts):
        # ─── RANGER V3 START: 11-ingest-region ───
        # Resolved before anything else: an unknown name must stop the command
        # before it touches the DB or the network, never fall through to Kenya.
        # (call_command(region=...) bypasses argparse choices, so check here too.)
        try:
            self.region = resolve_region(opts["region"])
        except ValueError as exc:
            raise CommandError(str(exc))
        self.region_name = opts["region"]
        # ─── RANGER V3 END: 11-ingest-region ───
        try:
            robot = Robot.objects.get(robot_id_str=opts["robot"])
        except Robot.DoesNotExist:
            raise CommandError(f"No robot with robot_id_str={opts['robot']!r}")

        self.robot = robot
        self.source = opts["source"]
        self.max_skew = opts["max_skew"]
        self.note = f"ros_bridge {opts['topic']} via rosbridge {opts['host']}:{opts['port']}"
        # ─── RANGER V3 START: 11-ingest-region ───
        self.note += f" · region={self.region_name}"
        if self.region_name == REGION_NONE:
            self.stderr.write(
                "WARNING: --region none — the inversion tripwire is OFF. "
                "Swapped lat/lon WILL be saved. Escape hatch only."
            )
        # ─── RANGER V3 END: 11-ingest-region ───
        self.counts = Counter()
        # ─── RANGER V3 START: 09-live-console ───
        self.broadcast_up = True
        # ─── RANGER V3 END: 09-live-console ───
        self.lock = threading.Lock()
        self.inbox = queue.Queue(maxsize=1000)
        # ─── RANGER V3 START: 13-reading-assembly ───
        self.readings = ReadingCache(ceiling=self.source)
        # ─── RANGER V3 END: 13-reading-assembly ───

        client = roslibpy.Ros(host=opts["host"], port=opts["port"])
        try:
            client.run(timeout=10)
        except Exception as exc:
            raise CommandError(f"Cannot reach rosbridge at {opts['host']}:{opts['port']}: {exc}")

        topic = roslibpy.Topic(client, opts["topic"], "sensor_msgs/msg/NavSatFix")
        topic.subscribe(self.on_fix)
        # ─── RANGER V3 START: 13-reading-assembly ───
        reading_topics = []
        for spec in SPECS:
            t = roslibpy.Topic(client, spec.topic, spec.msg_type,
                               throttle_rate=spec.throttle_ms)
            t.subscribe(lambda m, key=spec.key: self._enqueue(key, m))
            reading_topics.append(t)
        # ─── RANGER V3 END: 13-reading-assembly ───
        self.stdout.write(
            f"Connected. {opts['topic']} -> SensorLog for {robot.robot_id_str} "
            f"(source={self.source}, region={self.region_name}). Ctrl-C to stop."
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
                        self._dispatch(m)
                    except Exception as exc:
                        self._count("error")
                        self.stderr.write(f"ingest error: {exc!r}")
                if client.is_connected != connected:
                    connected = client.is_connected
                    self.stderr.write(f"rosbridge {'reconnected' if connected else 'DISCONNECTED'}")
        except KeyboardInterrupt:
            pass
        finally:
            topic.unsubscribe()
            for t in reading_topics:  # 13-reading-assembly
                t.unsubscribe()
            client.terminate()
            self.stdout.write(f"Stopped. {dict(self.counts)}")

    def _count(self, key):
        with self.lock:
            self.counts[key] += 1

    def on_fix(self, m):
        # Runs on roslibpy's Twisted reactor thread, which has an event loop:
        # Django raises SynchronousOnlyOperation for ORM calls there. Enqueue
        # only; the main (sync) thread does the DB writes.
        self._enqueue(FIX, m)

    # ─── RANGER V3 START: 13-reading-assembly ───
    def _enqueue(self, key, m):
        """Every topic shares ONE inbox, so the main thread sees fixes and
        readings in arrival order and the reading cache needs no lock."""
        try:
            self.inbox.put_nowait((key, m))
        except queue.Full:
            self._count("dropped")

    def _dispatch(self, item):
        key, m = item
        if key == FIX:
            return self._ingest(m)
        reason = self.readings.remember(key, m)
        if reason:
            self._count(f"{key}_{reason}")

    def _attach_readings(self, log, ts):
        """Inside the row's transaction. Returns labels for the log line."""
        fresh, stale = self.readings.take_fresh(ts)
        for key in stale:
            self._count(f"{key}_stale")
        tags = []
        for r in fresh:
            READING_MODELS[r.key].objects.create(sensor_log=log, source=r.source, **r.values)
            self._count(f"{r.key}_attached")
            tags.append(f"{r.key}:{r.source}")
        return tags
    # ─── RANGER V3 END: 13-reading-assembly ───

    def _ingest(self, m):
        status = (m.get("status") or {}).get("status", -1)
        if status < 0:
            return self._count("no_fix")

        lat, lon = m.get("latitude"), m.get("longitude")
        if lat is None or lon is None or math.isnan(lat) or math.isnan(lon):
            return self._count("no_coords")

        # 13-reading-assembly: one stamp parser for fixes and readings.
        ts = stamp_to_datetime(m) or datetime.fromtimestamp(0, tz=dt_tz.utc)
        skew = abs((timezone.now() - ts).total_seconds())
        if skew > self.max_skew:
            self.stderr.write(f"skip: robot clock skew {skew:.0f}s — is the Orin clock synced?")
            return self._count("clock_skew")

        try:
            point = point_from_latlon(lat=lat, lon=lon, region=self.region)  # F11
        except ValueError as exc:
            self.stderr.write(f"skip: {exc}")
            return self._count("out_of_region")

        close_old_connections()
        # ─── RANGER V3 START: 13-reading-assembly ───
        # Row + readings commit together or not at all: a row must never
        # exist without the readings it was written with, or vice versa.
        with transaction.atomic():
            log = SensorLog.objects.create(
                robot=self.robot,
                timestamp=ts,
                location=point,
                source=self.source,
                provenance_note=self.note,
            )
            tags = self._attach_readings(log, ts)
        # ─── RANGER V3 END: 13-reading-assembly ───
        self._count("saved")
        extra = f" + {' '.join(tags)}" if tags else ""
        self.stdout.write(f"SensorLog #{log.pk}: {lat:.6f}, {lon:.6f} [{self.source}] @ {ts:%H:%M:%S}Z{extra}")
        # ─── RANGER V3 START: 09-live-console ───
        self._broadcast(log)

    def _broadcast(self, log):
        """The DB row is the record; the socket is a view of it. A failed
        broadcast (Redis down) is counted, never fatal, and logged only on a
        state change so a dead Redis doesn't flood the terminal at 1 Hz.
        Invariant at Ctrl-C: saved == broadcast + broadcast_error."""
        try:
            broadcast_sensorlog(log)
        except Exception as exc:
            self._count("broadcast_error")
            if self.broadcast_up:
                self.broadcast_up = False
                self.stderr.write(f"broadcast DOWN (rows still saving): {exc!r}")
            return
        self._count("broadcast")
        if not self.broadcast_up:
            self.broadcast_up = True
            self.stderr.write("broadcast recovered")
        # ─── RANGER V3 END: 09-live-console ───
# ─── RANGER V3 END: 08-gps-ingest ───