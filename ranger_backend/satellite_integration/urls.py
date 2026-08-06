# ─── RANGER V3 START: satellite api urls ───
"""
Satellite EO routes (F10.2 CP6).

Included under /api/satellite/ from ranger_backend/urls.py, so the full paths
are /api/satellite/datasets/, /api/satellite/queries/, /api/satellite/images/,
and /api/satellite/coverage/.

Note the include prefix carries "satellite/" — unlike core.urls, which is
included at /api/ and spells the segment in each path. The satellite surface
is a whole namespace rather than four sibling endpoints, and F10.3 adds a
render route under the same prefix.
"""
from django.urls import path

from . import views

urlpatterns = [
    path(
        "datasets/",
        views.SatelliteDatasetListAPIView.as_view(),
        name="satellite-dataset-list",
    ),
    path(
        "datasets/<int:pk>/",
        views.SatelliteDatasetDetailAPIView.as_view(),
        name="satellite-dataset-detail",
    ),
    path(
        "queries/",
        views.SatelliteQueryListAPIView.as_view(),
        name="satellite-query-list",
    ),
    path(
        "queries/<int:pk>/",
        views.SatelliteQueryDetailAPIView.as_view(),
        name="satellite-query-detail",
    ),
    path(
        "images/",
        views.SatelliteImageListAPIView.as_view(),
        name="satellite-image-list",
    ),
    path(
        "images/<int:pk>/",
        views.SatelliteImageDetailAPIView.as_view(),
        name="satellite-image-detail",
    ),
    path(
        "coverage/",
        views.SatelliteCoverageAPIView.as_view(),
        name="satellite-coverage",
    ),
]
# ─── RANGER V3 END: satellite api urls ───
