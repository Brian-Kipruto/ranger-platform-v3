# ─── RANGER V3 START: 15-mission-plan ───
"""
Mission planning endpoints (F15 / Pass 6a).

  GET  /api/missions/        org's missions, newest first, paginated
  POST /api/missions/        create mission + ordered waypoints (one transaction)
  GET  /api/missions/<id>/   one mission with its waypoints
  PUT  /api/missions/<id>/   full replace (name, description, robot,
                             threshold_m, waypoints) — PENDING only, else 409

Plain DRF generics + IsAuthenticated, the accounts/core/satellite shape
(ADR-0007). Tenancy: Mission carries organization directly; every queryset
filters on it and a user with no org sees nothing. Another tenant's mission
is 404, never 403. Starting a mission (launch_mission) is 6b.
"""
from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from core.pagination import StandardResultsSetPagination

from .models import Mission
from .serializers import MissionSerializer, MissionWriteSerializer


def _org_missions(user):
    """Every Mission visible to `user`. Never unscoped."""
    organization = getattr(user, "organization", None)
    if organization is None:
        return Mission.objects.none()
    return (
        Mission.objects.filter(organization=organization)
        .select_related("robot")
        .prefetch_related("waypoints")
    )


class MissionListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination
    serializer_class = MissionSerializer

    def get_queryset(self):
        return _org_missions(self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        write = MissionWriteSerializer(data=request.data, context={"request": request})
        write.is_valid(raise_exception=True)
        mission = write.save()
        mission = _org_missions(request.user).get(pk=mission.pk)
        return Response(MissionSerializer(mission).data, status=status.HTTP_201_CREATED)


class MissionDetailAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = MissionSerializer
    http_method_names = ["get", "put", "head", "options"]  # full replace only

    def get_queryset(self):
        return _org_missions(self.request.user)

    def update(self, request, *args, **kwargs):
        self.get_object()  # 404 for another tenant, before anything else
        with transaction.atomic():
            # Lock, then re-check: a Start racing this PUT must win cleanly.
            mission = Mission.objects.select_for_update().get(pk=self.kwargs["pk"])
            if mission.status != Mission.Status.PENDING:
                return Response(
                    {"detail": f"Mission is {mission.status}; only PENDING missions can be edited."},
                    status=status.HTTP_409_CONFLICT,
                )
            write = MissionWriteSerializer(mission, data=request.data, context={"request": request})
            write.is_valid(raise_exception=True)
            write.save()
        mission = _org_missions(request.user).get(pk=mission.pk)
        return Response(MissionSerializer(mission).data)
# ─── RANGER V3 END: 15-mission-plan ───
