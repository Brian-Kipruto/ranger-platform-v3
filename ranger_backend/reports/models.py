# ─── RANGER V3 START: 16-report-model ───
"""
Compliance reports (F16).

A Report is an audit artifact: one PDF generated from one COMPLETED mission's
rows in Postgres, with the hashes needed to prove later that neither the PDF
nor the data embedded in it has changed.

Immutable by construction. Regenerating a mission's report creates a NEW row
and a NEW file; an existing row is never rewritten (save() refuses), because
a report someone already handed to a regulator must stay exactly what it was.

PROTECT on mission and organization: deleting a mission must not silently take
its reports with it. The organization is copied from the mission at
generation time so tenancy checks on download don't depend on the mission
row staying unchanged.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import SensorLog


class Report(models.Model):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="reports",
    )
    mission = models.ForeignKey(
        "missions.Mission",
        on_delete=models.PROTECT,
        related_name="reports",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_generated",
    )
    generated_at = models.DateTimeField(default=timezone.now, editable=False)
    format_version = models.CharField(
        max_length=20,
        help_text="REPORT_FORMAT_VERSION of the generator that wrote this.",
    )

    # Relative to MEDIA_ROOT, same pattern as SatelliteImage.cog_path. Never
    # serialized to clients; downloads go through a tenancy-checked view (7c).
    pdf_path = models.CharField(max_length=500)
    pdf_sha256 = models.CharField(max_length=64)
    # The mission's full data, embedded in the PDF as a CSV attachment.
    csv_sha256 = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField()

    # The least authoritative tier present across positions and every reading
    # kind in the report (F16 fork 7). Never the majority.
    weakest_source = models.CharField(
        max_length=10, choices=SensorLog.Source.choices
    )
    # Kind x tier counts, survey window, distinct citations, per-tier stats —
    # exactly what the PDF prints, so a report can be audited without
    # re-parsing it.
    summary = models.JSONField()

    class Meta:
        ordering = ["-generated_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "Reports are immutable. Generate a new report instead of "
                "editing this one."
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Report #{self.pk} — {self.mission.name} @ {self.generated_at:%Y-%m-%d %H:%M}"
# ─── RANGER V3 END: 16-report-model ───
