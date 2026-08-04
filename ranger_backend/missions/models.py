"""
─── RANGER V3 START: missions models ───
Mission planning: a Mission (org-scoped, assigned to a robot) and its
ordered Waypoints. Separates intent (the plan) from result (the sensor
logs collected, which FK back to Mission from core).

Geospatial (F10.1): Waypoint carries a PostGIS Point in `location` — the sole
source of truth, with latitude/longitude surviving as read-only properties
derived from it. Mission gains `area_of_interest`, a
nullable Polygon. The AOI is new — nothing to migrate from — and is what
satellite queries join against in F10.2. See ADR-0011.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models


class Mission(models.Model):
    """A planned operation for one robot, scoped to an Organization."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        PAUSED = "PAUSED", "Paused"
        COMPLETED = "COMPLETED", "Completed"
        ABORTED = "ABORTED", "Aborted"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="missions",
    )
    # Lazy string ref to core.Robot to keep the apps decoupled and avoid
    # any import ordering issues.
    robot = models.ForeignKey(
        "core.Robot",
        on_delete=models.PROTECT,
        related_name="missions",
    )
    # Who created the mission. Nullable so a deleted user doesn't take the
    # mission record with them.
    created_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        related_name="missions_created",
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    # ─── RANGER V3 START: F10.1 geometry ───
    # NEW in F10.1 (not a migration of anything — Mission had no geometry).
    # Nullable: existing missions have no defined AOI, and plenty never will.
    # F10.2's SatelliteQuery scopes scene retrieval to this polygon.
    area_of_interest = gis_models.PolygonField(
        srid=4326,
        null=True,
        blank=True,
        help_text="Optional WGS84 survey boundary. Scopes satellite scene "
                  "retrieval and ground-truth correlation (F10.2+).",
    )
    # ─── RANGER V3 END: F10.1 geometry ───

    # Arbitrary tenant-defined tags, same pattern as Robot.metadata.
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = (
            ("launch_mission", "Can start, pause, resume, and abort missions"),
        )

    def __str__(self) -> str:
        return f"{self.name} [{self.status}]"


class Waypoint(models.Model):
    """A single ordered geographic point within a Mission's path."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        SKIPPED = "SKIPPED", "Skipped"

    mission = models.ForeignKey(
        Mission,
        on_delete=models.CASCADE,
        related_name="waypoints",
    )

    order = models.PositiveIntegerField(
        help_text="Sequence position within the mission, 0-based."
    )

    # ─── RANGER V3 START: F10.1 geometry ───
    # Same treatment as SensorLog.location. Write via core.geo.point_from_latlon.
    location = gis_models.PointField(
        srid=4326,
        help_text="WGS84 target position. Source of truth for coordinates.",
    )
    # ─── RANGER V3 END: F10.1 geometry ───
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["mission", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["mission", "order"],
                name="unique_waypoint_order_per_mission",
            )
        ]

    # ─── RANGER V3 START: F10.1 derived coordinates ───
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
        return f"{self.mission.name} wp#{self.order}"

# ─── RANGER V3 END: missions models ───