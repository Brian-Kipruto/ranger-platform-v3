"""
─── RANGER V3 START: missions models ───
Mission planning: a Mission (org-scoped, assigned to a robot) and its
ordered Waypoints. Separates intent (the plan) from result (the sensor
logs collected, which FK back to Mission from core).
"""
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
    latitude = models.FloatField()
    longitude = models.FloatField()
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

    def __str__(self) -> str:
        return f"{self.mission.name} wp#{self.order}"

# ─── RANGER V3 END: missions models ───