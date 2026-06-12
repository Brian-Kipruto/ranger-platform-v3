# ─── RANGER V3 START: simulator ───
"""
run_simulation — generate realistic sensor data into the Feature 03 models.

Two modes:
  * backfill (default): generate --count historical SensorLogs in one shot,
    timestamps walking backward from now at --interval-seconds spacing, then exit.
    This is what the Data Explorer (Feature 05) needs to have rows to query.
  * live (--live): loop forever, writing one log every --live-delay seconds with
    a now() timestamp, until Ctrl-C. Writes to Postgres only — there is no Redis/
    WebSocket consumer wired in V3 yet, so nothing is broadcast.

Position is hybrid:
  * If the target robot has an IN_PROGRESS mission with PENDING waypoints, the
    sim drives toward the next waypoint, marks it COMPLETED on arrival, advances,
    and attaches each log to that mission.
  * Otherwise it random-walks around a start coordinate, with mission=None.

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
from missions.models import Mission, Waypoint

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

# How close (in degrees) the robot must get to a waypoint to count as "arrived".
# ~0.00015 deg latitude is roughly 16 m — a sensible arrival threshold for a
# ground robot at this simulation's step size.
WAYPOINT_ARRIVAL_THRESHOLD_DEG = 0.00015

# Per-step movement magnitudes, in degrees (~111 km per degree latitude).
RANDOM_WALK_STEP_DEG = 0.00010       # ~11 m jitter per log in random-walk
WAYPOINT_DRIVE_STEP_DEG = 0.00012    # ~13 m progress toward a waypoint per log


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
            "--clear",
            action="store_true",
            help="Delete ALL existing SensorLogs for the target robot before "
                 "generating (prompts for confirmation).",
        )

    # ── entry point ───────────────────────────────────────────────────────
    def handle(self, *args, **options):
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

        # Position state — start at the random-walk origin. If we end up driving a
        # mission, the first waypoint pass will pull us toward the route.
        self._lat = options["start_lat"]
        self._lon = options["start_lon"]
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
    def _run_backfill(self, robot, count, interval_seconds):
        mission, waypoints, wp_index = self._load_active_route(robot)
        mode = "waypoint-driving" if mission else "random-walk"
        self.stdout.write(
            f"Backfilling {count} log(s), {interval_seconds}s apart, mode: {mode}"
            + (f" (mission '{mission.name}')" if mission else "")
        )

        # Timestamps walk backward from now so the newest log is ~now.
        now = timezone.now()
        created = 0
        for i in range(count):
            # Oldest first → newest last, so positions/values evolve forward in time.
            steps_from_oldest = count - 1 - i
            ts = now - timedelta(seconds=interval_seconds * steps_from_oldest)

            if mission and wp_index < len(waypoints):
                wp_index = self._step_toward_waypoint(
                    mission, waypoints, wp_index, ts
                )
            else:
                mission = None  # route exhausted → finish as random-walk
                self._step_random_walk()

            self._write_log(robot, mission, ts)
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Backfill complete: {created} SensorLog(s) written.")
        )

    def _run_live(self, robot, delay):
        mission, waypoints, wp_index = self._load_active_route(robot)
        mode = "waypoint-driving" if mission else "random-walk"
        self.stdout.write(
            self.style.SUCCESS(
                f"Live mode (every {delay}s), mode: {mode}"
                + (f" (mission '{mission.name}')" if mission else "")
                + ". Ctrl-C to stop."
            )
        )
        written = 0
        try:
            while True:
                ts = timezone.now()
                if mission and wp_index < len(waypoints):
                    wp_index = self._step_toward_waypoint(
                        mission, waypoints, wp_index, ts
                    )
                else:
                    if mission:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Mission '{mission.name}' route complete — "
                                "continuing as random-walk."
                            )
                        )
                        mission = None
                    self._step_random_walk()

                self._write_log(robot, mission, ts)
                written += 1
                self.stdout.write(
                    f"[{written}] {ts:%H:%M:%S} "
                    f"({self._lat:.5f}, {self._lon:.5f})"
                )
                time.sleep(delay)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nStopped. {written} live SensorLog(s) written."
                )
            )

    # ── route handling ────────────────────────────────────────────────────
    def _load_active_route(self, robot):
        """Find an IN_PROGRESS mission with PENDING waypoints for this robot.

        Returns (mission, waypoints_list, start_index) or (None, [], 0).
        Org scoping is implicit: we already hold this robot, and the mission FK
        is to this robot, so robot.missions is correct (ADR 0006 — no org field
        on the log, tenancy comes through robot).
        """
        mission = (
            robot.missions.filter(status=Mission.Status.IN_PROGRESS)
            .order_by("-created_at")
            .first()
        )
        if not mission:
            return None, [], 0

        waypoints = list(mission.waypoints.order_by("order"))
        if not waypoints:
            return None, [], 0

        # Start at the first not-yet-completed waypoint.
        start_index = 0
        for idx, wp in enumerate(waypoints):
            if wp.status == Waypoint.Status.PENDING:
                start_index = idx
                break
        else:
            # All waypoints already done → nothing to drive.
            return None, [], 0

        # Seed position near the first target so the route looks coherent.
        first = waypoints[start_index]
        self._lat = first.latitude
        self._lon = first.longitude
        return mission, waypoints, start_index

    def _step_toward_waypoint(self, mission, waypoints, wp_index, ts):
        """Move one step toward waypoints[wp_index]; mark COMPLETED on arrival.

        Returns the (possibly advanced) wp_index.
        """
        target = waypoints[wp_index]
        d_lat = target.latitude - self._lat
        d_lon = target.longitude - self._lon
        dist = math.hypot(d_lat, d_lon)

        if dist <= WAYPOINT_ARRIVAL_THRESHOLD_DEG:
            # Arrived — snap to the waypoint, mark it done, advance.
            self._lat = target.latitude
            self._lon = target.longitude
            if target.status != Waypoint.Status.COMPLETED:
                target.status = Waypoint.Status.COMPLETED
                target.save(update_fields=["status"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  waypoint #{target.order} COMPLETED "
                        f"@ {ts:%H:%M:%S}"
                    )
                )
            return wp_index + 1

        # Move a fixed step along the bearing to the target (with light jitter so
        # the path isn't a ruler-straight line).
        bearing = math.atan2(d_lon, d_lat)
        self._lat += WAYPOINT_DRIVE_STEP_DEG * math.cos(bearing)
        self._lon += WAYPOINT_DRIVE_STEP_DEG * math.sin(bearing)
        self._lat += random.uniform(-1, 1) * RANDOM_WALK_STEP_DEG * 0.15
        self._lon += random.uniform(-1, 1) * RANDOM_WALK_STEP_DEG * 0.15
        return wp_index

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
    def _write_log(self, robot, mission, ts):
        """Create the parent SensorLog + only the reading rows the robot supports.

        Reading models use primary_key=True on their OneToOne to SensorLog, so the
        parent MUST be created first (carry-forward from Feature 03).
        """
        self._step_values()

        log = SensorLog.objects.create(
            robot=robot,
            mission=mission,
            timestamp=ts,
            latitude=self._lat,
            longitude=self._lon,
        )

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