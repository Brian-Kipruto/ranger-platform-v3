"""
─── RANGER V3 START: core models ───
Core domain models: the robot fleet, a sensor catalog, and the decoupled
sensor-log structure (lean parent + per-sensor reading tables).

Tenancy: Robot carries the Organization FK. SensorLog and the reading
models inherit their tenant THROUGH the robot (no own organization FK) —
a log cannot belong to a different org than the robot that produced it.
Org-scoped queries on logs go via robot__organization=...

Geospatial (F10.1): `location` (PostGIS Point, WGS84) is the SOLE source of
truth for coordinates. The legacy latitude/longitude float columns are gone;
the names survive as read-only properties derived from the geometry, so the
API contract, CSV export, and admin are unchanged. See ADR-0011.

Never construct a Point directly — use core.geo.point_from_latlon, which
takes keyword-only arguments and cannot be called with lat/lon transposed.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models


class SensorType(models.Model):
    """Catalog of every sensor the platform can support (Geiger counter,
    PM sensor, IMU, etc.). Robots declare which of these they carry."""

    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Stable machine identifier, e.g. 'geiger', 'pm', 'imu_baro'.",
    )
    unit = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Primary unit of measurement, e.g. 'CPM', 'µg/m³'.",
    )
    description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Robot(models.Model):
    """A single robot in the fleet, scoped to one Organization.

    Primary key is the default integer (BigAutoField). The human-readable
    identifier is robot_id_str — a separate unique field, never the PK.
    """

    class Status(models.TextChoices):
        OFFLINE = "OFFLINE", "Offline"
        ONLINE = "ONLINE", "Online"
        MISSION = "MISSION", "On mission"
        MAINTENANCE = "MAINTENANCE", "Maintenance"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="robots",
    )

    name = models.CharField(max_length=200)
    robot_id_str = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Human-readable unique ID, e.g. 'RANGER-PRIME-001'.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
    )

    installed_sensors = models.ManyToManyField(
        SensorType,
        related_name="robots",
        blank=True,
        help_text="Which sensor types are physically installed on this robot.",
    )

    # Arbitrary tenant-defined tags (e.g. {"client": "Farm X", "team": "Alpha"})
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.robot_id_str})"


class SensorLog(models.Model):
    """Lean parent log entry: who/what/where/when. The actual sensor
    readings live in the decoupled OneToOne reading models below."""

    robot = models.ForeignKey(
        Robot,
        on_delete=models.CASCADE,
        related_name="sensor_logs",
    )
    # Lazy string ref to avoid a core<->missions circular import.
    mission = models.ForeignKey(
        "missions.Mission",
        on_delete=models.SET_NULL,
        related_name="sensor_logs",
        null=True,
        blank=True,
    )

    timestamp = models.DateTimeField(db_index=True)

    # ─── RANGER V3 START: F10.1 geometry ───
    # PostGIS Point, WGS84. GiST-indexed (spatial_index defaults True) so
    # ST_Within / ST_Intersects against satellite footprints use an index
    # scan rather than a seq scan (F10.4 correlation).
    #
    # ALWAYS write via core.geo.point_from_latlon — never a bare Point(),
    # which takes (lon, lat) and inverts silently.
    location = gis_models.PointField(
        srid=4326,
        help_text="WGS84 position of this reading. Source of truth for "
                  "coordinates; latitude/longitude are derived from it.",
    )
    # ─── RANGER V3 END: F10.1 geometry ───

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        permissions = (
            ("export_sensorlog", "Can export sensor log records"),
            ("view_livedata", "Can access real-time data streams"),
            ("view_visualization", "Can view charts/visualizations"),
            ("view_organization_data", "Can view data for own organization"),
            ("view_all_data", "Can view data across all organizations"),
        )

    # ─── RANGER V3 START: F10.1 derived coordinates ───
    # These were columns until F10.1's 0007 migration. They are properties now
    # so that DataLogSerializer, the CSV export header, the Data Explorer table,
    # and the admin all keep working unchanged against `location`.
    #
    # NOTE: being properties, they cannot be used in .filter() / .order_by() /
    # .values(). Nothing in the codebase did (verified by grep at F10.1); any
    # future spatial query should use `location` and PostGIS lookups anyway.
    @property
    def latitude(self) -> float | None:
        """Latitude in degrees north, derived from `location`."""
        return self.location.y if self.location else None

    @property
    def longitude(self) -> float | None:
        """Longitude in degrees east, derived from `location`."""
        return self.location.x if self.location else None
    # ─── RANGER V3 END: F10.1 derived coordinates ───

    def __str__(self) -> str:
        return f"{self.robot.robot_id_str} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"


class RadiationLog(models.Model):
    """Radiation readings for a SensorLog."""

    sensor_log = models.OneToOneField(
        SensorLog,
        on_delete=models.CASCADE,
        related_name="radiation_data",
        primary_key=True,
    )
    radiation_value = models.FloatField(help_text="Counts per minute (CPM).")
    dose_rate_usvh = models.FloatField(
        null=True, blank=True, help_text="Dose rate in µSv/h."
    )

    def __str__(self) -> str:
        return f"Radiation {self.radiation_value} CPM"


class AirQualityLog(models.Model):
    """Particulate readings for a SensorLog."""

    sensor_log = models.OneToOneField(
        SensorLog,
        on_delete=models.CASCADE,
        related_name="air_quality_data",
        primary_key=True,
    )
    pm25 = models.FloatField(null=True, blank=True, help_text="PM2.5 µg/m³.")
    pm10 = models.FloatField(null=True, blank=True, help_text="PM10 µg/m³.")

    def __str__(self) -> str:
        return f"PM2.5 {self.pm25} / PM10 {self.pm10}"


class ImuBaroLog(models.Model):
    """IMU + barometer readings for a SensorLog."""

    sensor_log = models.OneToOneField(
        SensorLog,
        on_delete=models.CASCADE,
        related_name="imu_baro_data",
        primary_key=True,
    )
    roll = models.FloatField(null=True, blank=True)
    pitch = models.FloatField(null=True, blank=True)
    yaw = models.FloatField(null=True, blank=True)
    pressure_baro = models.FloatField(null=True, blank=True, help_text="hPa.")
    altitude_baro = models.FloatField(null=True, blank=True, help_text="Metres.")

    def __str__(self) -> str:
        return f"IMU r{self.roll} p{self.pitch} y{self.yaw}"

# ─── RANGER V3 END: core models ───