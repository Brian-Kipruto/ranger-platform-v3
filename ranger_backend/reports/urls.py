# ─── RANGER V3 START: 16-report-download ───
"""Report routes, included under /api/ (full paths /api/reports/...)."""
from django.urls import path

from . import views

urlpatterns = [
    path("reports/", views.ReportListCreateAPIView.as_view(), name="report-list"),
    path("reports/<int:pk>/pdf/", views.ReportFileAPIView.as_view(), {"kind": "pdf"}, name="report-pdf"),
    path("reports/<int:pk>/csv/", views.ReportFileAPIView.as_view(), {"kind": "csv"}, name="report-csv"),
]
# ─── RANGER V3 END: 16-report-download ───
