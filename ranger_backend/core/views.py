# ─── RANGER V3 START: data explorer views ───
"""
Data Explorer read endpoints over core.SensorLog.

Four endpoints, all org-scoped and authenticated-only (matching the
established accounts/views.py pattern — plain DRF generics, IsAuthenticated,
no custom permission checks; the model-level custom perms from Feature 03
are gated in a later feature, see ADR 0007):

  GET /api/data-logs/         paginated list   (table feed)
  GET /api/data-logs/export/  CSV, unpaginated (download)
  GET /api/chart-data/        unpaginated, point-capped, ASC (charts)
  GET /api/map-data/          GeoJSON FeatureCollection, point-capped (map)

Tenancy (ADR 0006): SensorLog has no organization field. Every queryset
scopes through robot__organization=request.user.organization. Verified
against the live DB: 230 rows for ByteAnza via exactly this filter.
"""
import csv
from datetime import datetime, timedelta

from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import SensorLog
from .pagination import StandardResultsSetPagination
from .serializers import DataLogSerializer

# Safeguard: cap unpaginated chart/map payloads. If a filtered set exceeds
# this, we return the most-recent N (V2 §3.1.4 strategy).
MAX_CHART_POINTS = 5000


def _base_org_queryset(user):
    """The org-scoped, relation-prefetched base queryset shared by every
    endpoint. Tenancy resolves through the robot (ADR 0006); a log's org is
    its robot's org, so there is no SensorLog.organization to filter on."""
    return (
        SensorLog.objects.filter(robot__organization=user.organization)
        .select_related("robot", "mission")
        .prefetch_related(
            "radiation_data", "air_quality_data", "imu_baro_data"
        )
    )


def _apply_filters(qs, params):
    """Apply the four V2-parity filters (V2 §3.1.4). Dates are inclusive;
    date_end extends to end-of-day so a same-day start==end still matches.
    Bad date strings are ignored rather than erroring the whole request."""
    robot_id = params.get("robot_id")
    if robot_id:
        try:
            qs = qs.filter(robot_id=int(robot_id))
        except (TypeError, ValueError):
            qs = qs.none()  # bad robot_id → empty result, not a 500

    mission_id = params.get("mission_id")
    if mission_id:
        try:
            qs = qs.filter(mission_id=int(mission_id))
        except (TypeError, ValueError):
            qs = qs.none()  # bad mission_id → empty result, not a 500

    date_start = params.get("date_start")
    if date_start:
        try:
            d = datetime.strptime(date_start, "%Y-%m-%d")
            qs = qs.filter(timestamp__gte=d)
        except ValueError:
            pass

    date_end = params.get("date_end")
    if date_end:
        try:
            d = datetime.strptime(date_end, "%Y-%m-%d") + timedelta(days=1)
            qs = qs.filter(timestamp__lt=d)  # < next midnight == inclusive end-of-day
        except ValueError:
            pass

    return qs


class DataLogListAPIView(generics.ListAPIView):
    """GET /api/data-logs/ — paginated, org-scoped, filterable. Newest first."""

    serializer_class = DataLogSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = _base_org_queryset(self.request.user)
        qs = _apply_filters(qs, self.request.query_params)
        return qs.order_by("-timestamp")


class ChartDataListAPIView(generics.ListAPIView):
    """GET /api/chart-data/ — unpaginated, oldest-first, point-capped.
    Time-series charts need chronological order and the full filtered set."""

    serializer_class = DataLogSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        qs = _base_org_queryset(self.request.user)
        qs = _apply_filters(qs, self.request.query_params)
        qs = qs.order_by("timestamp")
        total = qs.count()
        if total > MAX_CHART_POINTS:
            # Keep the most-recent MAX_CHART_POINTS, still returned ascending.
            keep_ids = list(
                qs.order_by("-timestamp")
                .values_list("id", flat=True)[:MAX_CHART_POINTS]
            )
            qs = (
                _base_org_queryset(self.request.user)
                .filter(id__in=keep_ids)
                .order_by("timestamp")
            )
        return qs


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def data_log_export_csv(request):
    """GET /api/data-logs/export/ — same filters as the list, no pagination,
    chronological, streamed as a CSV attachment. JWT-authed (the 05b button
    does an axios blob download with the Bearer header), so it works in
    production where there is no session cookie — diverging deliberately from
    V2's session-cookie window.open approach."""
    qs = _base_org_queryset(request.user)
    qs = _apply_filters(qs, request.query_params)
    qs = qs.order_by("timestamp")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="ranger_sensor_logs.csv"'

    fieldnames = [
        "id", "robot_id_str", "robot_name", "mission_id", "mission_name",
        "timestamp", "latitude", "longitude",
        "radiation_value", "dose_rate_usvh",
        "pm25", "pm10",
        "roll", "pitch", "yaw", "pressure_baro", "altitude_baro",
    ]
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()

    # Reuse the serializer so CSV cells and JSON rows agree exactly (same
    # null-safe reading access).
    for row in DataLogSerializer(qs, many=True).data:
        writer.writerow(row)

    return response


class MapDataAPIView(generics.GenericAPIView):
    """GET /api/map-data/ — GeoJSON FeatureCollection of the full filtered
    track, point-capped. Decoupled from table pagination so the map can show
    the whole path while the table pages independently. Thin properties
    payload (enough to color markers / fill a popup) rather than every field."""

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        qs = _base_org_queryset(self.request.user)
        qs = _apply_filters(qs, self.request.query_params)
        qs = qs.order_by("timestamp")
        if qs.count() > MAX_CHART_POINTS:
            keep_ids = list(
                qs.order_by("-timestamp")
                .values_list("id", flat=True)[:MAX_CHART_POINTS]
            )
            qs = (
                _base_org_queryset(self.request.user)
                .filter(id__in=keep_ids)
                .order_by("timestamp")
            )
        return qs

    def get(self, request, *args, **kwargs):
        features = []
        for log in self.get_queryset():
            rad = getattr(log, "radiation_data", None)
            air = getattr(log, "air_quality_data", None)
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [log.longitude, log.latitude],  # GeoJSON: lng, lat
                },
                "properties": {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat(),
                    "radiation_value": rad.radiation_value if rad is not None else None,
                    "pm25": air.pm25 if air is not None else None,
                },
            })
        return Response(
            {"type": "FeatureCollection", "features": features},
            status=status.HTTP_200_OK,
        )
# ─── RANGER V3 END: data explorer views ───