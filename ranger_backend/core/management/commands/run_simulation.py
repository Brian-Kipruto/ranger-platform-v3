# ─── RANGER V3 START: simulator ───
"""
run_simulation — generate realistic sensor data into the Feature 03 models.

Two modes:
  * backfill (default): generate --count historical SensorLogs in one shot,
    timestamps walking backward from now at --interval-seconds spacing, then exit.
    This is what the Data Explorer (Feature 05) needs to have rows to query.
  * live (--live): loop forever, writing one log every --live-delay seconds with
    a now() timestamp, until Ctrl-C. Each saved row is broadcast to the live
    console (F15; failures counted, rows kept). Backfill never broadcasts.

Position is hybrid:
  * If the target robot has an IN_PROGRESS mission with PENDING waypoints, the
    sim drives toward the active (first PENDING) waypoint at --speed m/s.
  * Otherwise it random-walks around a start coordinate.

F15 (6b.3): the sim NEVER decides completion. Every row is offered to
missions.progress.advance inside its transaction — the same decider, threshold
and completed_at rule as ros_ingest — and attached to the mission advance
reports. A step that would reach the target lands exactly on it, so a long
step can't jump the threshold circle. --live broadcasts every saved row
(ros_bridge.broadcast, ros_ingest's failure policy), so the console sees the
fallback live. --region picks the guard box; rows are labelled SIMULATED.

Readings written per SensorLog are driven by the robot's installed_sensors
(matched on SensorType.code): geiger -> RadiationLog, pm -> AirQualityLog,
imu_baro -> ImuBaroLog. A robot with none of these recognised codes gets a
SensorLog with no reading rows (a warning is printed once).

Tenancy (ADR 0006): SensorLog has no organization field; it inherits through
robot. We already hold the robot object here, so the active-mission lookup is
robot.missions.filter(...), and no organization field is ever set on a log.
"""
import math
import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Robot,
    SensorType,
    SensorLog,
    RadiationLog,
    AirQualityLog,
    ImuBaroLog,
)
from core.geo import point_from_latlon
from missions.models import Mission, Waypoint
# ─── RANGER V3 START: 15-sim-advance ───
from core.geo import RABAT_VENUE, resolve_region
from missions.progress import advance
from ros_bridge.broadcast import broadcast_sensorlog
# ─── RANGER V3 END: 15-sim-advance ───

# Sensor codes we know how to simulate, mapped to the reading model they fill.
# Anything on the robot outside these codes is ignored for reading generation.
RADIATION_CODE = "geiger"
AIR_QUALITY_CODE = "pm"
IMU_BARO_CODE = "imu_baro"

# Default random-walk origin: Nairobi (matches the operator's locale / V2 default
# spirit). Overridable via --start-lat / --start-lon.
DEFAULT_START_LAT = -1.2921
DEFAULT_START_LON = 36.8219

# Default target robot identity if --robot is omitted and we must create one.
DEFAULT_ROBOT_ID_STR = "RANGER-PRIME-001"
DEFAULT_ROBOT_NAME = "North Field Bot"
DEFAULT_ORG_SLUG = "byteanza"

# Per-step random-walk magnitude, in degrees (~111 km per degree latitude).
RANDOM_WALK_STEP_DEG = 0.00010       # ~11 m jitter per log in random-walk

# ─── RANGER V3 START: 15-sim-advance ───
# Mission driving is in metres (F15). Completion is NOT decided here.
M_PER_DEG = 111_320.0
DEFAULT_SPEED_MS = 2.0
LEAD_IN_M = 15.0          # start this far south of the first pending waypoint
REGION_START = {"kenya": (DEFAULT_START_LAT, DEFAULT_START_LON), "rabat": RABAT_VENUE}
# ─── RANGER V3 END: 15-sim-advance ───


class Command(BaseCommand):
    help = (
        "Generate realistic sensor data into the core models. "
        "Backfills historical logs by default; use --live for a continuous loop."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--robot",
            dest="robot_id_str",
            default=None,
            help="robot_id_str of the target robot. Default: first robot found, "
                 f"or get-or-create '{DEFAULT_ROBOT_ID_STR}' under "
                 f"org '{DEFAULT_ORG_SLUG}'.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=200,
            help="Backfill mode: number of SensorLogs to generate (default 200).",
        )
        parser.add_argument(
            "--interval-seconds",
            type=int,
            default=30,
            help="Backfill mode: seconds between successive log timestamps "
                 "(default 30).",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Live mode: loop forever writing one log every --live-delay "
                 "seconds (Ctrl-C to stop) instead of backfilling.",
        )
        parser.add_argument(
            "--live-delay",
            type=float,
            default=3.0,
            help="Live mode: seconds between writes (default 3.0, V2 parity).",
        )
        parser.add_argument(
            "--start-lat",
            type=float,
            default=DEFAULT_START_LAT,
            help=f"Random-walk origin latitude (default {DEFAULT_START_LAT}).",
        )
        parser.add_argument(
            "--start-lon",
            type=float,
            default=DEFAULT_START_LON,
            help=f"Random-walk origin longitude (default {DEFAULT_START_LON}).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Seed the RNG for reproducible output. Two runs with the same "
                 "--seed, --count, --start-lat/lon and robot produce identical "
                 "positions and readings — needed for stable test fixtures and "
                 "for regenerating demo data deterministically (F10.4).",
        )
        # ─── RANGER V3 START: 15-sim-advance ───
        parser.add_argument(
            "--speed", type=float, default=DEFAULT_SPEED_MS,
            help=f"Mission driving speed, m/s (default {DEFAULT_SPEED_MS}). Step per row = "
                 "speed x --live-delay (live) or x --interval-seconds (backfill).",
        )
        parser.add_argument(
            "--region", choices=sorted(REGION_START), default="kenya",
            help="Guard box for every written point (default kenya). With rabat and "
                 "no --start-lat/lon, the random walk starts at the Rabat venue.",
        )
        # ─── RANGER V3 END: 15-sim-advance ───
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete ALL existing SensorLogs for the target robot before "
                 "generating (prompts for confirmation).",
        )

    # ── entry point ───────────────────────────────────────────────────────
    def handle(self, *args, **options):
        # ─── RANGER V3 START: F10.1 deterministic mode ───
        if options["seed"] is not None:
            random.seed(options["seed"])
            self.stdout.write(self.style.WARNING(
                f"RNG seeded with {options['seed']} — output is deterministic."
            ))
        # ─── RANGER V3 END: F10.1 deterministic mode ───

        robot = self._resolve_robot(options["robot_id_str"])
        self.stdout.write(
            self.style.SUCCESS(f"Target robot: {robot.name} ({robot.robot_id_str})")
        )

        # Which reading models can we fill for this robot?
        self._reading_codes = self._resolve_reading_codes(robot)
        if not self._reading_codes:
            self.stdout.write(
                self.style.WARNING(
                    "Robot has no recognised sensor codes (geiger/pm/imu_baro). "
                    "SensorLogs will be written with NO reading rows."
                )
            )
        else:
            self.stdout.write(
                f"Will generate readings for: {', '.join(sorted(self._reading_codes))}"
            )

        if options["clear"]:
            self._clear_logs(robot)

        # ─── RANGER V3 START: 15-sim-advance ───
        self._region = resolve_region(options["region"])
        if options["speed"] <= 0:
            raise CommandError("--speed must be > 0")
        self._speed = options["speed"]
        self._driving = None      # mission pk we have positioned for
        self._broadcast_up = True
        self.counts = {"saved": 0, "broadcast": 0, "broadcast_error": 0,
                       "wp_completed": 0, "mission_completed": 0}
        # Position state — start at the random-walk origin (per region).
        start = (options["start_lat"], options["start_lon"])
        if options["region"] != "kenya" and start == (DEFAULT_START_LAT, DEFAULT_START_LON):
            start = REGION_START[options["region"]]
        self._lat, self._lon = start
        # ─── RANGER V3 END: 15-sim-advance ───
        # Mutable sensor baselines for smooth random-walk of values.
        self._cpm = random.uniform(15.0, 25.0)
        self._pm25 = random.uniform(5.0, 35.0)
        self._yaw = random.uniform(0.0, 360.0)

        if options["live"]:
            self._run_live(robot, options["live_delay"])
        else:
            self._run_backfill(
                robot, options["count"], options["interval_seconds"]
            )

    # ── robot / sensor resolution ─────────────────────────────────────────
    def _resolve_robot(self, robot_id_str):
        if robot_id_str:
            try:
                return Robot.objects.get(robot_id_str=robot_id_str)
            except Robot.DoesNotExist:
                raise CommandError(
                    f"No robot with robot_id_str='{robot_id_str}'. "
                    "Omit --robot to use/seed the default, or create it in admin."
                )

        existing = Robot.objects.first()
        if existing:
            return existing

        # No robots at all — seed the default under the default org.
        # Imported lazily so a missing accounts app surfaces clearly.
        from accounts.models import Organization

        try:
            org = Organization.objects.get(slug=DEFAULT_ORG_SLUG)
        except Organization.DoesNotExist:
            raise CommandError(
                f"No robots exist and no Organization with slug "
                f"'{DEFAULT_ORG_SLUG}' to attach a seed robot to. "
                "Create an organization (and ideally a robot) in admin first."
            )

        robot = Robot.objects.create(
            organization=org,
            name=DEFAULT_ROBOT_NAME,
            robot_id_str=DEFAULT_ROBOT_ID_STR,
            status=Robot.Status.ONLINE,
        )
        # Attach geiger + pm so the seed robot produces meaningful readings.
        for code, name, unit in (
            (RADIATION_CODE, "Geiger Counter", "CPM"),
            (AIR_QUALITY_CODE, "PM Sensor", "µg/m³"),
        ):
            st, _ = SensorType.objects.get_or_create(
                code=code, defaults={"name": name, "unit": unit}
            )
            robot.installed_sensors.add(st)
        self.stdout.write(
            self.style.WARNING(
                f"No robots existed — seeded {robot.name} ({robot.robot_id_str}) "
                f"under '{org.slug}' with geiger + pm sensors."
            )
        )
        return robot

    def _resolve_reading_codes(self, robot):
        """Return the set of recognised sensor codes installed on the robot."""
        installed = set(
            robot.installed_sensors.values_list("code", flat=True)
        )
        recognised = {RADIATION_CODE, AIR_QUALITY_CODE, IMU_BARO_CODE}
        return installed & recognised

    def _clear_logs(self, robot):
        qs = SensorLog.objects.filter(robot=robot)
        count = qs.count()
        if count == 0:
            self.stdout.write("--clear: no existing logs for this robot.")
            return
        confirm = input(
            f"--clear will DELETE {count} SensorLog(s) for "
            f"{robot.robot_id_str} (and their readings via cascade). "
            "Type 'yes' to proceed: "
        )
        if confirm.strip().lower() != "yes":
            raise CommandError("Aborted at --clear confirmation.")
        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.WARNING(f"--clear: deleted {deleted} row(s).")
        )

    # ── mode runners ──────────────────────────────────────────────────────
    # ─── RANGER V3 START: 15-sim-advance ───
    def _run_backfill(self, robot, count, interval_seconds):
        step_m = self._speed * interval_seconds
        self.stdout.write(f"Backfilling {count} log(s), {interval_seconds}s apart, mission step {step_m:.0f} m")
        # Timestamps walk backward from now so the newest log is ~now.
        now = timezone.now()
        for i in range(count):
            # Oldest first -> newest last, so positions/values evolve forward in time.
            ts = now - timedelta(seconds=interval_seconds * (count - 1 - i))
            self._move(robot, step_m)
            self._write_log(robot, ts)
        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete: {self.counts['saved']} SensorLog(s) written, "
            f"{self.counts['wp_completed']} waypoint(s) completed."
        ))

    def _run_live(self, robot, delay):
        step_m = self._speed * delay
        self.stdout.write(self.style.SUCCESS(
            f"Live mode (every {delay}s, mission step {step_m:.1f} m). Ctrl-C to stop."
        ))
        try:
            while True:
                ts = timezone.now()
                self._move(robot, step_m)
                log = self._write_log(robot, ts)
                self._broadcast(log)
                self.stdout.write(f"[{self.counts['saved']}] {ts:%H:%M:%S} ({self._lat:.6f}, {self._lon:.6f})")
                time.sleep(delay)
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS(f"\nStopped. {self.counts}"))

    def _broadcast(self, log):
        """ros_ingest's policy: the row is the record, the socket a view of it.
        A failed broadcast is counted, never fatal; logged on state change."""
        try:
            broadcast_sensorlog(log)
        except Exception as exc:
            self.counts["broadcast_error"] += 1
            if self._broadcast_up:
                self._broadcast_up = False
                self.stderr.write(f"broadcast DOWN (rows still saving): {exc!r}")
            return
        self.counts["broadcast"] += 1
        if not self._broadcast_up:
            self._broadcast_up = True
            self.stderr.write("broadcast recovered")

    # ── route handling (positions only; completion is missions.progress) ──
    @staticmethod
    def _active_target(robot):
        """(mission, active waypoint) of the robot's running mission, or (None, None).
        Read fresh every step: the DB, via advance, is the only source of progress."""
        mission = robot.missions.filter(status=Mission.Status.IN_PROGRESS).first()
        if mission is None:
            return None, None
        wp = mission.waypoints.filter(status=Waypoint.Status.PENDING).order_by("order").first()
        return (mission, wp) if wp else (None, None)

    def _move(self, robot, step_m):
        mission, target = self._active_target(robot)
        if target is None:
            self._driving = None
            self._step_random_walk()
            return
        tlat, tlon = target.location.y, target.location.x
        if self._driving != mission.pk:
            # New mission: begin a lead-in south of its active waypoint (not on it).
            self._driving = mission.pk
            self._lat, self._lon = tlat - LEAD_IN_M / M_PER_DEG, tlon
            self.stdout.write(f"Driving mission #{mission.pk} '{mission.name}' from {LEAD_IN_M:.0f} m south of wp {target.order + 1}")
            return
        kx = M_PER_DEG * math.cos(math.radians(self._lat))
        dy = (tlat - self._lat) * M_PER_DEG
        dx = (tlon - self._lon) * kx
        dist = math.hypot(dx, dy)
        if dist <= step_m:
            # Land exactly on the target: a long step can't jump the threshold
            # circle. Whether this completes it is advance()'s call, not ours.
            self._lat, self._lon = tlat, tlon
            return
        self._lat += dy / dist * step_m / M_PER_DEG
        self._lon += dx / dist * step_m / kx
    # ─── RANGER V3 END: 15-sim-advance ───

    def _step_random_walk(self):
        """Nudge position by a small random amount in both axes."""
        self._lat += random.uniform(-1, 1) * RANDOM_WALK_STEP_DEG
        self._lon += random.uniform(-1, 1) * RANDOM_WALK_STEP_DEG

    # ── value generation + write ──────────────────────────────────────────
    def _step_values(self):
        """Advance the sensor value baselines as a smooth random walk."""
        # Radiation: drift around baseline, rare spike.
        self._cpm += random.uniform(-1.5, 1.5)
        if random.random() < 0.03:
            self._cpm += random.uniform(20.0, 60.0)  # transient hot spot
        self._cpm = max(5.0, min(self._cpm, 300.0))

        # PM2.5: drift, clamp to plausible ambient range.
        self._pm25 += random.uniform(-2.0, 2.0)
        self._pm25 = max(2.0, min(self._pm25, 150.0))

        # Yaw: slow heading drift, wrap 0–360.
        self._yaw = (self._yaw + random.uniform(-8.0, 8.0)) % 360.0

    @transaction.atomic
    def _write_log(self, robot, ts):
        """Create the parent SensorLog + only the reading rows the robot supports.

        Reading models use primary_key=True on their OneToOne to SensorLog, so the
        parent MUST be created first (carry-forward from Feature 03).
        """
        self._step_values()

        # ─── RANGER V3 START: F10.1 geometry write ───
        # point_from_latlon is keyword-only and asserts the Kenya bbox, so a
        # transposed lat/lon raises here instead of silently writing a point
        # in the Indian Ocean. This is the pattern the ROS bridge (F08/F09)
        # and satellite ingestion (F10.2) must follow too.
        # ─── RANGER V3 START: 15-sim-advance ───
        point = point_from_latlon(lat=self._lat, lon=self._lon, region=self._region)
        adv = advance(robot, point, ts)  # the one decider — same as ros_ingest
        log = SensorLog.objects.create(
            robot=robot,
            mission=adv.mission if adv else None,
            timestamp=ts,
            location=point,
            source=SensorLog.Source.SIMULATED,
        )
        self.counts["saved"] += 1
        if adv and adv.completed:
            self.counts["wp_completed"] += 1
            done = " · MISSION COMPLETED" if adv.mission_completed else ""
            self.counts["mission_completed"] += 1 if adv.mission_completed else 0
            self.stdout.write(self.style.SUCCESS(
                f"  mission #{adv.mission.pk} wp {adv.waypoint.order + 1} COMPLETED "
                f"({adv.distance_m:.1f} m) @ {ts:%H:%M:%S}{done}"
            ))
        # ─── RANGER V3 END: 15-sim-advance ───
        # ─── RANGER V3 END: F10.1 geometry write ───

        if RADIATION_CODE in self._reading_codes:
            RadiationLog.objects.create(
                sensor_log=log,
                radiation_value=round(self._cpm, 2),
                dose_rate_usvh=round(self._cpm * 0.0057, 4),
            )
        if AIR_QUALITY_CODE in self._reading_codes:
            pm10 = self._pm25 * random.uniform(1.5, 2.0)
            AirQualityLog.objects.create(
                sensor_log=log,
                pm25=round(self._pm25, 2),
                pm10=round(pm10, 2),
            )
        if IMU_BARO_CODE in self._reading_codes:
            ImuBaroLog.objects.create(
                sensor_log=log,
                roll=round(random.uniform(-5.0, 5.0), 3),
                pitch=round(random.uniform(-5.0, 5.0), 3),
                yaw=round(self._yaw, 3),
                pressure_baro=round(random.uniform(1008.0, 1018.0), 2),
                altitude_baro=round(random.uniform(1600.0, 1700.0), 2),
            )
        return log
# ─── RANGER V3 END: simulator ───