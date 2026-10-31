# ─── RANGER V3 START: 16-report-download ───
"""
Compliance report API (F16 / 7c). Tenancy follows missions/views.py:
every queryset is the caller's org; another org's report or mission is a
404, never a 403, so existence never leaks across tenants.

  GET  /api/reports/                     the org's reports, newest first
  POST /api/reports/  {"mission": id}    generate (reports.generate_report)
  GET  /api/reports/<id>/pdf/            download, integrity-checked
  GET  /api/reports/<id>/csv/            download, integrity-checked

Downloads re-hash the file and compare with the hash stored at generation.
A file that no longer matches is refused (409), never served: a report that
has been altered on disk is not the report the row describes.
"""
import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardResultsSetPagination
from missions.models import Mission

from .generate import REPORTS_SUBDIR, ReportError, generate_report
from .models import Report
from .serializers import ReportSerializer

log = logging.getLogger(__name__)

GENERATE_PERM = "reports.generate_report"
FILES = {
    "pdf": ("pdf_path", "pdf_sha256", "application/pdf"),
    "csv": ("csv_path", "csv_sha256", "text/csv; charset=utf-8"),
}


def _org_reports(user):
    """Every Report visible to `user`. Never unscoped."""
    organization = getattr(user, "organization", None)
    if organization is None:
        return Report.objects.none()
    return (
        Report.objects.filter(organization=organization)
        .select_related("mission", "mission__robot", "generated_by")
    )


class ReportListCreateAPIView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination
    serializer_class = ReportSerializer

    def get_queryset(self):
        return _org_reports(self.request.user)

    def post(self, request):
        if not request.user.has_perm(GENERATE_PERM):
            return Response({"detail": f"Needs {GENERATE_PERM}."}, status=status.HTTP_403_FORBIDDEN)
        try:
            mission_id = int(request.data.get("mission"))
        except (TypeError, ValueError):
            return Response({"mission": ["A mission id is required."]}, status=status.HTTP_400_BAD_REQUEST)
        organization = getattr(request.user, "organization", None)
        mission = (
            Mission.objects.filter(pk=mission_id, organization=organization)
            .select_related("organization", "robot").first()
            if organization is not None else None
        )
        if mission is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            report = generate_report(mission, user=request.user)
        except ReportError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ReportFileAPIView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk: int, kind: str):
        report = _org_reports(request.user).filter(pk=pk).first()
        if report is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        path_field, sha_field, content_type = FILES[kind]
        rel = getattr(report, path_field)
        if not rel:
            return Response(
                {"detail": "This report predates CSV download. Generate a new report for this mission."},
                status=status.HTTP_404_NOT_FOUND,
            )

        root = (Path(settings.MEDIA_ROOT) / REPORTS_SUBDIR).resolve()
        path = (Path(settings.MEDIA_ROOT) / rel).resolve()
        if root not in path.parents:  # a stored path must never leave reports/
            log.error("report %s %s path escapes reports root: %r", report.pk, kind, rel)
            return Response({"detail": "Report file path is invalid."}, status=status.HTTP_409_CONFLICT)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            log.error("report %s %s missing on disk: %s", report.pk, kind, rel)
            return Response({"detail": "Report file is missing on the server."}, status=status.HTTP_409_CONFLICT)

        actual = hashlib.sha256(data).hexdigest()
        expected = getattr(report, sha_field)
        if actual != expected:
            log.error("report %s %s integrity failure: expected %s, got %s", report.pk, kind, expected, actual)
            return Response(
                {"detail": "Integrity check failed: the file on the server no longer matches "
                           "the hash recorded when this report was generated. It will not be served."},
                status=status.HTTP_409_CONFLICT,
            )

        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{path.name}"'
        response["X-Ranger-Sha256"] = actual
        response["Cache-Control"] = "private, no-store"
        return response
# ─── RANGER V3 END: 16-report-download ───
