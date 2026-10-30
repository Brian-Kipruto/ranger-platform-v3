# ─── RANGER V3 START: 16-report-generate ───
"""
generate_report(mission) -> Report. Synchronous (F16 fork 2).

Built from Postgres, not the live stream: the same mission produces the same
numbers every time. Only COMPLETED missions — a report over a mission still
taking data could not be reproduced.

All-or-nothing: the PDF is written to a temp file beside its destination,
fsynced, renamed into place, and the Report row is created after. If the row
fails, the file is removed. A row never points at a missing file, and a
failed run leaves no file behind.
"""
import hashlib
import io
import logging
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from core.exports import write_sensor_log_csv
from core.models import SensorLog
from missions.models import Mission

from . import stats
from .models import Report

# Bump when the PDF's content or layout changes meaningfully. Printed in the
# PDF and stored on the row, so any report can be traced to its generator.
REPORT_FORMAT_VERSION = "16.7a"

REPORTS_SUBDIR = "reports"


class ReportError(Exception):
    """The mission cannot be reported on as it stands. Message is user-facing."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mission_rows(mission):
    """The mission's rows, scoped to the mission's org through the robot.

    Defence in depth (ADR-0006): a row on this mission from another org's
    robot is a data-integrity fault, and a report must not quietly include
    or quietly drop it. Refuse instead.
    """
    qs = SensorLog.objects.filter(mission=mission)
    foreign = qs.exclude(robot__organization_id=mission.organization_id).count()
    if foreign:
        raise ReportError(
            f"Mission {mission.pk} has {foreign} sensor log(s) from robots "
            f"outside its organization. Refusing to report on it."
        )
    return qs


def _csv_text(qs) -> str:
    full = (
        qs.select_related("robot", "mission")
        .prefetch_related("radiation_data", "air_quality_data", "imu_baro_data")
        .order_by("timestamp", "id")
    )
    buf = io.StringIO()
    write_sensor_log_csv(buf, full)
    return buf.getvalue()


def _write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def render_pdf(html: str, csv_text: str, csv_name: str) -> bytes:
    # Imported here so `manage.py check` and unrelated tests never load the
    # pango/cairo stack.
    from weasyprint import HTML, Attachment

    # Dev settings log at DEBUG; fontTools then writes thousands of lines per
    # report (one per font table subset). Keep warnings, drop the noise.
    logging.getLogger("fontTools").setLevel(logging.WARNING)

    return HTML(string=html).write_pdf(
        attachments=[Attachment(string=csv_text, name=csv_name)]
    )


def generate_report(mission: Mission, *, user=None) -> Report:
    if mission.status != Mission.Status.COMPLETED:
        raise ReportError(
            f"Mission {mission.pk} is {mission.status}. Reports are generated "
            f"from COMPLETED missions only."
        )

    qs = _mission_rows(mission)
    rows = list(qs.order_by("timestamp", "id").values(*stats.ROW_COLUMNS))
    if not rows:
        raise ReportError(f"Mission {mission.pk} has no sensor logs.")

    summary = stats.summarise(rows)
    csv_text = _csv_text(qs)
    csv_sha = _sha256(csv_text.encode("utf-8"))

    generated_at = timezone.now()
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    csv_name = f"mission-{mission.pk}-{stamp}-data.csv"

    html = render_to_string("reports/report.html", {
        "mission": mission,
        "organization": mission.organization,
        "robot": mission.robot,
        "generated_at": generated_at,
        "generated_by": user,
        "format_version": REPORT_FORMAT_VERSION,
        "summary": summary,
        "tiers": stats.TIERS,
        # Templates can't index a dict by a variable: flatten for the table.
        "matrix_rows": [
            (kind, [counts[t] for t in stats.TIERS])
            for kind, counts in summary["provenance_matrix"].items()
        ],
        "csv_name": csv_name,
        "csv_sha256": csv_sha,
    })
    pdf = render_pdf(html, csv_text, csv_name)
    pdf_sha = _sha256(pdf)

    rel = Path(REPORTS_SUBDIR) / mission.organization.slug / (
        f"mission-{mission.pk}-{stamp}-{pdf_sha[:8]}.pdf"
    )
    dest = Path(settings.MEDIA_ROOT) / rel
    _write_atomic(dest, pdf)

    try:
        with transaction.atomic():
            return Report.objects.create(
                organization=mission.organization,
                mission=mission,
                generated_by=user,
                generated_at=generated_at,
                format_version=REPORT_FORMAT_VERSION,
                pdf_path=str(rel),
                pdf_sha256=pdf_sha,
                csv_sha256=csv_sha,
                row_count=summary["row_count"],
                weakest_source=summary["weakest_source"],
                summary=summary,
            )
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
# ─── RANGER V3 END: 16-report-generate ───
