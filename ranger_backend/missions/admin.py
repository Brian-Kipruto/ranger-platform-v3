"""
─── RANGER V3 START: missions admin ───
Admin registration for missions. Waypoints are edited inline on a Mission,
ordered by their sequence position.
"""
from django.contrib import admin

from .models import Mission, Waypoint


class WaypointInline(admin.TabularInline):
    model = Waypoint
    extra = 0
    ordering = ("order",)


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "robot", "status", "created_by", "created_at")
    list_filter = ("status", "organization")
    search_fields = ("name",)
    date_hierarchy = "created_at"
    inlines = (WaypointInline,)

# ─── RANGER V3 END: missions admin ───