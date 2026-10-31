# ─── RANGER V3 START: 16-report-download ───
"""Report list rows. File paths are NEVER serialized: downloads go through
the tenancy- and integrity-checked file endpoint, never MEDIA_URL."""
from rest_framework import serializers

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    mission_name = serializers.CharField(source="mission.name", read_only=True)
    robot_id_str = serializers.CharField(source="mission.robot.robot_id_str", read_only=True)
    generated_by = serializers.SerializerMethodField()
    has_csv = serializers.SerializerMethodField()
    registry_version = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "id", "mission", "mission_name", "robot_id_str",
            "generated_at", "generated_by", "format_version",
            "row_count", "weakest_source",
            "pdf_sha256", "csv_sha256", "has_csv", "registry_version",
        )
        read_only_fields = fields

    def get_generated_by(self, obj) -> str | None:
        return obj.generated_by.username if obj.generated_by_id else None

    def get_has_csv(self, obj) -> bool:
        return bool(obj.csv_path)

    def get_registry_version(self, obj) -> str | None:
        return (obj.summary or {}).get("comparisons", {}).get("registry_version")
# ─── RANGER V3 END: 16-report-download ───
