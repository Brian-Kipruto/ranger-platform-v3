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
from django.db.models import Count
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import SensorLog
from .pagination import StandardResultsSetPagination
from .serializers import DataLogSerializer

# Safeguard: cap unpaginated chart/map payloads. If a filtered set exceeds
# this, we return the most-recent N (V2 §3.1.4 strategy).
MAX_CHART_POINTS = 5000

# Distinct provenance_note strings returned in the map summary. Seven Marsabit
# sites produce seven; the ceiling exists so an unfiltered multi-tenant set
# cannot turn a summary into a dump.
NOTE_SUMMARY_LIMIT = 12


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
        "id", "robot_id", "robot_id_str", "robot_name", "mission_id", "mission_name",
        "timestamp", "latitude", "longitude",
        # F10.2: provenance travels with every exported row. An export that
        # loses its labels is exactly how modelled data gets mistaken for
        # measured data downstream.
        "source", "provenance_note",
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

    def get_filtered_queryset(self):
        """The FULL filtered set, uncapped.

        Split out from get_queryset (which caps) because the provenance
        summary must describe every row the user's filters select, not the
        5,000 the map happens to draw. Summarising the capped sample and
        presenting it as the set is how a banner ends up claiming things
        about data it never looked at.
        """
        qs = _base_org_queryset(self.request.user)
        qs = _apply_filters(qs, self.request.query_params)
        return qs.order_by("timestamp")

    def get_queryset(self):
        qs = self.get_filtered_queryset()
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
                    # GeoJSON is [lng, lat] — which is exactly PostGIS (x, y),
                    # so this reads straight off the geometry with no flip.
                    # F10.1: was [log.longitude, log.latitude] over float columns.
                    "type": "Point",
                    "coordinates": [log.location.x, log.location.y],
                },
                "properties": {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat(),
                    "radiation_value": rad.radiation_value if rad is not None else None,
                    "pm25": air.pm25 if air is not None else None,
                    # F10.2: lets the map badge markers by provenance, so
                    # modelled points are visibly distinct from measured ones
                    # without the user opening anything.
                    "source": log.source,
                    # F10.3 CP0: the tier alone says MODELLED; the note says
                    # modelled from WHAT. A label without a citation is a
                    # disclaimer, not provenance — and the Data Explorer's
                    # banner quotes this verbatim for an all-modelled set.
                    "provenance_note": log.provenance_note,
                },
            })
        return Response(
            {
                "type": "FeatureCollection",
                "features": features,
                # ─── RANGER V3 START: map provenance summary (F10.3 CP0.5) ───
                "provenance": self._provenance_summary(len(features)),
                # ─── RANGER V3 END: map provenance summary (F10.3 CP0.5) ───
            },
            status=status.HTTP_200_OK,
        )

    def _provenance_summary(self, returned):
        """Provenance over the FULL filtered set, not the capped sample.

        Two aggregates on the uncapped queryset:
          by_source  tier -> count, so the UI states a number it checked
          notes      distinct provenance_note strings

        `notes` is a LIST because a multi-site filter spans several citations
        (one Table 3.1 row per site). The frontend must not pick one and
        present it as the set's citation — quoting Boji's n and mean over a
        set that is mostly Dukana is a wrong citation, which is worse than no
        citation, because it reads as authoritative and does not survive
        anyone opening the actual table.

        Capped at a sane number: a set spanning hundreds of distinct notes is
        one the banner should summarise, not enumerate.
        """
        qs = self.get_filtered_queryset()

        counts = (
            qs.values("source")
            .annotate(n=Count("id"))
            .order_by()
        )
        by_source = {row["source"]: row["n"] for row in counts}
        total = sum(by_source.values())

        # .order_by() with NO argument is load-bearing, not tidying.
        # get_filtered_queryset() orders by timestamp; chaining .distinct()
        # onto an ordered queryset makes Django add the ordering column to
        # the SELECT, so Postgres runs `SELECT DISTINCT provenance_note,
        # timestamp` and every row is distinct because every timestamp is.
        # 1,819 Forole points sharing ONE citation came back as 1,819
        # citations, and the banner reported "12+" instead of quoting the
        # single real one. Clear the ordering first.
        notes = list(
            qs.order_by()
            .exclude(provenance_note="")
            .values_list("provenance_note", flat=True)
            .distinct()[:NOTE_SUMMARY_LIMIT + 1]
        )
        notes_truncated = len(notes) > NOTE_SUMMARY_LIMIT
        notes = notes[:NOTE_SUMMARY_LIMIT]

        return {
            "total": total,
            "by_source": by_source,
            "notes": notes,
            "notes_truncated": notes_truncated,
            # The map drew `returned` of `total`. Surfacing this is what lets
            # the status line stop saying "MAP SHOWS FULL TRACK" when it does
            # not.
            "returned": returned,
            "truncated": returned < total,
        }
# ─── RANGER V3 END: data explorer views ───