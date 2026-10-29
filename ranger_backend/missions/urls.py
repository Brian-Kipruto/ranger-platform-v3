# ─── RANGER V3 START: 15-mission-plan ───
"""Mission planning routes, included under /api/ (full paths /api/missions/...)."""
from django.urls import path

from . import views

urlpatterns = [
    path("missions/", views.MissionListCreateAPIView.as_view(), name="mission-list"),
    path("missions/<int:pk>/", views.MissionDetailAPIView.as_view(), name="mission-detail"),
    # ─── RANGER V3 START: 15-mission-advance ───
    path("missions/<int:pk>/start/", views.MissionStartAPIView.as_view(), name="mission-start"),
    # ─── RANGER V3 END: 15-mission-advance ───
]
# ─── RANGER V3 END: 15-mission-plan ───
