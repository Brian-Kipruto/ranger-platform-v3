"""
─── RANGER V3 START: core admin ───
Admin registration for core models. The three decoupled reading models
are exposed as inlines on SensorLog so you edit a log and its readings
in one place.
"""
from django.contrib import admin

from .models import (
    SensorType,
    Robot,
    SensorLog,
    RadiationLog,
    AirQualityLog,
    ImuBaroLog,
)


class RadiationLogInline(admin.StackedInline):
    model = RadiationLog
    can_delete = True
    extra = 0


class AirQualityLogInline(admin.StackedInline):
    model = AirQualityLog
    can_delete = True
    extra = 0


class ImuBaroLogInline(admin.StackedInline):
    model = ImuBaroLog
    can_delete = True
    extra = 0


@admin.register(SensorType)
class SensorTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "unit")
    search_fields = ("name", "code")


@admin.register(Robot)
class RobotAdmin(admin.ModelAdmin):
    list_display = ("name", "robot_id_str", "organization", "status")
    list_filter = ("status", "organization")
    search_fields = ("name", "robot_id_str")
    filter_horizontal = ("installed_sensors",)


@admin.register(SensorLog)
class SensorLogAdmin(admin.ModelAdmin):
    list_display = ("robot", "mission", "timestamp", "latitude", "longitude")
    list_filter = ("robot__organization", "robot", "mission")
    search_fields = ("robot__robot_id_str",)
    date_hierarchy = "timestamp"
    inlines = (RadiationLogInline, AirQualityLogInline, ImuBaroLogInline)

# ─── RANGER V3 END: core admin ───