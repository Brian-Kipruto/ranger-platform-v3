# ─── RANGER V3 START: 15-mission-plan ───
"""
Mission planning serializers (F15 / Pass 6a).

Read and write shapes are separate on purpose:

  * MissionSerializer        — what the console sees. Waypoints as {lat, lon}.
  * MissionWriteSerializer   — what the console sends. organization and
    created_by are NEVER accepted from the payload; the view sets them from
    the request. The robot is addressed by robot_id_str, the identifier the
    console already holds (VITE_VIDEO_ROBOT_ID, the teleop socket), and is
    resolved against the caller's org only, so a foreign robot is "does not
    exist", not "forbidden" (no existence leak).

Waypoints are named {lat, lon} objects, never positional pairs, and every
point goes through core.geo.point_from_latlon. All waypoints must fall inside
ONE known region: a swapped Nairobi point lands in the Mediterranean and a
swapped Rabat point lands in Tanzania, outside both boxes, so inversion is
still caught without the caller naming a region.
"""
from django.db import transaction
from rest_framework import serializers

from core.geo import REGIONS, point_from_latlon
from core.models import Robot

from .models import THRESHOLD_M_MAX, THRESHOLD_M_MIN, Mission, Waypoint

MAX_WAYPOINTS = 50


class WaypointSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="latitude", read_only=True)
    lon = serializers.FloatField(source="longitude", read_only=True)

    class Meta:
        model = Waypoint
        fields = ("id", "order", "lat", "lon", "status", "completed_at")
        read_only_fields = fields


class MissionSerializer(serializers.ModelSerializer):
    robot_id_str = serializers.CharField(source="robot.robot_id_str", read_only=True)
    waypoints = WaypointSerializer(many=True, read_only=True)

    class Meta:
        model = Mission
        fields = (
            "id", "name", "description", "robot", "robot_id_str", "status",
            "threshold_m", "started_at", "completed_at",
            "created_at", "updated_at", "waypoints",
        )
        read_only_fields = fields


class WaypointInSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90.0, max_value=90.0)
    lon = serializers.FloatField(min_value=-180.0, max_value=180.0)


def _points_in_one_region(waypoints):
    """[{lat, lon}, ...] -> [Point, ...], all inside the same known region.
    Raises ValidationError otherwise."""
    for bbox in REGIONS.values():
        try:
            return [point_from_latlon(lat=w["lat"], lon=w["lon"], region=bbox) for w in waypoints]
        except ValueError:
            continue
    raise serializers.ValidationError(
        "All waypoints must lie inside one known region "
        f"({', '.join(REGIONS)}). Check lat/lon order."
    )


class MissionWriteSerializer(serializers.ModelSerializer):
    robot_id_str = serializers.SlugRelatedField(
        source="robot", slug_field="robot_id_str", queryset=Robot.objects.none()
    )
    threshold_m = serializers.FloatField(
        min_value=THRESHOLD_M_MIN, max_value=THRESHOLD_M_MAX, required=False
    )
    waypoints = WaypointInSerializer(many=True, min_length=1, max_length=MAX_WAYPOINTS)

    class Meta:
        model = Mission
        fields = ("name", "description", "robot_id_str", "threshold_m", "waypoints")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = getattr(self.context["request"].user, "organization", None)
        # Tenancy: only the caller's robots resolve. No org -> nothing resolves.
        self.fields["robot_id_str"].queryset = (
            Robot.objects.filter(organization=org) if org else Robot.objects.none()
        )

    def validate_waypoints(self, value):
        self._points = _points_in_one_region(value)
        return value

    def _write_waypoints(self, mission):
        Waypoint.objects.bulk_create(
            Waypoint(mission=mission, order=i, location=p) for i, p in enumerate(self._points)
        )

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("waypoints")
        user = self.context["request"].user
        mission = Mission.objects.create(
            organization=user.organization, created_by=user, **validated_data
        )
        self._write_waypoints(mission)
        return mission

    def update(self, instance, validated_data):
        """Full replace. Caller holds the row lock and has checked PENDING."""
        validated_data.pop("waypoints")
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        instance.waypoints.all().delete()
        self._write_waypoints(instance)
        return instance
# ─── RANGER V3 END: 15-mission-plan ───
