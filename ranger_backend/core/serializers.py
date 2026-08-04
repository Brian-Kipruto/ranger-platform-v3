# ─── RANGER V3 START: data explorer serializer ───
"""
Read-only serializer for the Data Explorer, CSV export, chart-data, and
map-data endpoints.

CRITICAL — null safety: a SensorLog may have NO reading of a given type.
The simulator writes only the reading models matching a robot's
installed_sensors, so the seed robot (geiger + pm, no imu_baro) produces
~230 logs that have radiation_data and air_quality_data but NO
imu_baro_data. V2's serializer used source='radiation_data.radiation_value',
which RAISES when the related object is missing. Here every reading field
comes through a SerializerMethodField guarded with getattr(obj, '<related>',
None), so an absent reading nulls its whole group cleanly instead of crashing.

Output shape is FLAT (all reading fields top-level) so TanStack Table
accessor keys and Recharts dataKeys map directly with no client-side
flatten step.

F10.1: latitude/longitude are no longer model FIELDS — they are properties
derived from SensorLog.location (PostGIS Point). ModelSerializer cannot infer
a serializer field from a property, so both are declared explicitly as
ReadOnlyField. Meta.fields is UNCHANGED, which is what keeps the API contract,
the CSV header, and the Data Explorer table identical across the migration.
"""
from rest_framework import serializers

from .models import SensorLog


class DataLogSerializer(serializers.ModelSerializer):
    # Parent / relations
    robot_id = serializers.IntegerField(source="robot.id", read_only=True)
    robot_id_str = serializers.CharField(source="robot.robot_id_str", read_only=True)
    robot_name = serializers.CharField(source="robot.name", read_only=True)
    mission_id = serializers.IntegerField(source="mission.id", read_only=True, allow_null=True)
    mission_name = serializers.CharField(source="mission.name", read_only=True, allow_null=True)

    # ─── RANGER V3 START: F10.1 derived coordinates ───
    # Model properties over `location`, not columns. ReadOnlyField reads the
    # attribute off the instance, so the emitted JSON is byte-identical to the
    # pre-migration output.
    latitude = serializers.ReadOnlyField()
    longitude = serializers.ReadOnlyField()
    # ─── RANGER V3 END: F10.1 derived coordinates ───

    # Radiation (null if no radiation_data)
    radiation_value = serializers.SerializerMethodField()
    dose_rate_usvh = serializers.SerializerMethodField()

    # Air quality (null if no air_quality_data)
    pm25 = serializers.SerializerMethodField()
    pm10 = serializers.SerializerMethodField()

    # IMU / baro (null if no imu_baro_data — the seed robot's case)
    roll = serializers.SerializerMethodField()
    pitch = serializers.SerializerMethodField()
    yaw = serializers.SerializerMethodField()
    pressure_baro = serializers.SerializerMethodField()
    altitude_baro = serializers.SerializerMethodField()

    class Meta:
        model = SensorLog
        fields = [
            "id",
            "robot_id",
            "robot_id_str",
            "robot_name",
            "mission_id",
            "mission_name",
            "timestamp",
            "latitude",
            "longitude",
            "radiation_value",
            "dose_rate_usvh",
            "pm25",
            "pm10",
            "roll",
            "pitch",
            "yaw",
            "pressure_baro",
            "altitude_baro",
        ]

    # ─── reading getters (all getattr-guarded) ───
    def get_radiation_value(self, obj):
        r = getattr(obj, "radiation_data", None)
        return r.radiation_value if r is not None else None

    def get_dose_rate_usvh(self, obj):
        r = getattr(obj, "radiation_data", None)
        return r.dose_rate_usvh if r is not None else None

    def get_pm25(self, obj):
        a = getattr(obj, "air_quality_data", None)
        return a.pm25 if a is not None else None

    def get_pm10(self, obj):
        a = getattr(obj, "air_quality_data", None)
        return a.pm10 if a is not None else None

    def get_roll(self, obj):
        i = getattr(obj, "imu_baro_data", None)
        return i.roll if i is not None else None

    def get_pitch(self, obj):
        i = getattr(obj, "imu_baro_data", None)
        return i.pitch if i is not None else None

    def get_yaw(self, obj):
        i = getattr(obj, "imu_baro_data", None)
        return i.yaw if i is not None else None

    def get_pressure_baro(self, obj):
        i = getattr(obj, "imu_baro_data", None)
        return i.pressure_baro if i is not None else None

    def get_altitude_baro(self, obj):
        i = getattr(obj, "imu_baro_data", None)
        return i.altitude_baro if i is not None else None
# ─── RANGER V3 END: data explorer serializer ───