# ─── RANGER V3 START: data explorer urls ───
"""
Data Explorer routes. Included under /api/ from ranger_backend/urls.py, so
the full paths are /api/data-logs/, /api/data-logs/export/, /api/chart-data/,
and /api/map-data/.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("data-logs/", views.DataLogListAPIView.as_view(), name="data-log-list"),
    path("data-logs/export/", views.data_log_export_csv, name="data-log-export-csv"),
    path("chart-data/", views.ChartDataListAPIView.as_view(), name="chart-data-list"),
    path("map-data/", views.MapDataAPIView.as_view(), name="map-data"),
]
# ─── RANGER V3 END: data explorer urls ───