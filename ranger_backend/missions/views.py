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
from django.db import IntegrityError, transaction
# ─── RANGER V3 START: 15-mission-advance ───
from django.utils import timezone
from rest_framework.views import APIView
# ─── RANGER V3 END: 15-mission-advance ───
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


# ─── RANGER V3 START: 15-mission-advance ───
class MissionStartAPIView(APIView):
    """POST /api/missions/<id>/start/ — PENDING -> IN_PROGRESS (F15 fork 3).

    404 another tenant's mission (checked first, so a 403 can't confirm it
    exists); 403 without missions.launch_mission; 409 if not PENDING or the
    robot already has a running mission. From here ros_ingest advances it.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        if not _org_missions(request.user).filter(pk=pk).exists():
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.has_perm("missions.launch_mission"):
            return Response({"detail": "Needs missions.launch_mission."}, status=status.HTTP_403_FORBIDDEN)
        try:
            with transaction.atomic():
                mission = Mission.objects.select_for_update().get(pk=pk)
                if mission.status != Mission.Status.PENDING:
                    return Response(
                        {"detail": f"Mission is {mission.status}; only PENDING missions can be started."},
                        status=status.HTTP_409_CONFLICT,
                    )
                mission.status = Mission.Status.IN_PROGRESS
                mission.started_at = timezone.now()
                mission.save(update_fields=["status", "started_at", "updated_at"])
        except IntegrityError:  # one_in_progress_mission_per_robot
            return Response(
                {"detail": "This robot already has a mission in progress."},
                status=status.HTTP_409_CONFLICT,
            )
        mission = _org_missions(request.user).get(pk=pk)
        return Response(MissionSerializer(mission).data)
# ─── RANGER V3 END: 15-mission-advance ───
