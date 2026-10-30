# ─── RANGER V3 START: 16-report-model ───
from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Read-only. Reports are generated, never hand-made or edited."""

    list_display = (
        "id", "organization", "mission", "weakest_source", "row_count",
        "generated_at", "format_version",
    )
    list_filter = ("organization", "weakest_source")
    readonly_fields = [f.name for f in Report._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
# ─── RANGER V3 END: 16-report-model ───
