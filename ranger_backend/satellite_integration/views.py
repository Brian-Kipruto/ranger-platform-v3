# ─── RANGER V3 START: satellite api views ───
"""
Read-only satellite EO endpoints (F10.2 CP6).

    GET /api/satellite/datasets/        catalog list      GLOBAL, no org filter
    GET /api/satellite/datasets/<id>/   catalog detail
    GET /api/satellite/queries/         org-scoped list
    GET /api/satellite/queries/<id>/    detail, with nested images
    GET /api/satellite/images/          org-scoped list
    GET /api/satellite/images/<id>/     detail
    GET /api/satellite/coverage/        GeoJSON FeatureCollection of footprints

Plain DRF generics, IsAuthenticated, no custom permission classes — the same
shape as accounts/views.py and core/views.py. Model-level permissions remain
ungated; ADR-0007 is still open and F10.5 is where it closes.

TENANCY — the asymmetry, and why it is deliberate
--------------------------------------------------
Three models, three different answers, each following an existing precedent:

  * SatelliteDataset has NO organization. Sentinel-2 is Sentinel-2 for every
    tenant; the catalog is global reference data, like SensorType. Filtering
    it per-org would imply each tenant has a private view of the sky.
  * SatelliteQuery carries `organization` DIRECTLY — the Mission pattern. A
    query is initiated by an org and spends real EECU quota, so the org that
    spent it owns the record.
  * SatelliteImage has no org field at all and scopes through
    `query__organization` — structurally identical to SensorLog scoping
    through `robot__organization` (ADR-0006).

Everything read here goes through `_org_queries` or `_org_images`. Neither
returns an unscoped queryset under any circumstances, including for a user
with no organization, which resolves to empty rather than to everything.
"""
import json
from datetime import datetime, timedelta

from django.contrib.gis.geos import GEOSException
from django.utils import timezone
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response

from core.geo import polygon_from_bbox
from core.pagination import StandardResultsSetPagination

from . import cog, render
from .models import SatelliteDataset, SatelliteImage, SatelliteQuery
from .serializers import (
    SatelliteDatasetSerializer,
    SatelliteImageSerializer,
    SatelliteQueryDetailSerializer,
    SatelliteQuerySerializer,
)

# Footprints are a handful of polygons per org, not thousands of points, so
# the coverage endpoint needs no equivalent of MAX_CHART_POINTS. This cap is a
# backstop against a runaway ingest, not a display strategy.
MAX_COVERAGE_FEATURES = 2000


def _org_queries(user):
    """Every SatelliteQuery visible to `user`. Never unscoped."""
    organization = getattr(user, "organization", None)
    if organization is None:
        # A user with no org sees nothing, not everything. The failure mode
        # this guards is a misconfigured account silently gaining god-mode.
        return SatelliteQuery.objects.none()
    return (
        SatelliteQuery.objects.filter(organization=organization)
        .select_related("dataset", "mission")
    )


def _org_images(user):
    """Every SatelliteImage visible to `user`, scoped through its query."""
    organization = getattr(user, "organization", None)
    if organization is None:
        return SatelliteImage.objects.none()
    return (
        SatelliteImage.objects.filter(query__organization=organization)
        .select_related("dataset", "query")
    )


def _parse_bbox(raw: str):
    """Parse "west,south,east,north" into a WGS84 Polygon, or None.

    Returns None on anything malformed. Callers turn that into an EMPTY
    result rather than an ignored filter — deliberately unlike the date
    handling in core/views.py, which ignores unparseable input. A dropped date
    filter shows you extra rows; a dropped SPATIAL filter shows you imagery
    from somewhere you did not ask about, on a map, looking authoritative.
    """
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError:
        return None
    if west >= east or south >= north:
        return None
    try:
        return polygon_from_bbox(west, south, east, north)
    except (GEOSException, ValueError):
        return None


def _day_bound(raw: str):
    """Parse YYYY-MM-DD into an aware datetime at local midnight, or None.

    `acquisition_date` is timezone-aware and TIME_ZONE is Africa/Nairobi.
    Comparing a naive datetime against it makes Django guess — it warns, then
    assumes the project timezone. The guess happens to be right, which is
    worse than it being wrong: the behaviour is correct only by coincidence of
    configuration, and would shift by three hours if TIME_ZONE ever changed.
    Say what we mean instead.
    """
    try:
        return timezone.make_aware(datetime.strptime(raw, "%Y-%m-%d"))
    except ValueError:
        return None


def _filter_images(qs, params):
    """dataset code, query id, acquisition date range, and bbox intersection."""
    dataset_code = params.get("dataset")
    if dataset_code:
        qs = qs.filter(dataset__code=dataset_code)

    query_id = params.get("query")
    if query_id:
        try:
            qs = qs.filter(query_id=int(query_id))
        except (TypeError, ValueError):
            qs = qs.none()

    date_start = params.get("date_start")
    if date_start:
        start = _day_bound(date_start)
        if start is not None:
            qs = qs.filter(acquisition_date__gte=start)

    date_end = params.get("date_end")
    if date_end:
        end = _day_bound(date_end)
        if end is not None:
            # < next local midnight, so an inclusive end date matches scenes
            # acquired on that day.
            qs = qs.filter(acquisition_date__lt=end + timedelta(days=1))

    raw_bbox = params.get("bbox")
    if raw_bbox:
        aoi = _parse_bbox(raw_bbox)
        # See _parse_bbox: a malformed spatial filter must not silently widen
        # the result set.
        qs = qs.filter(geometry__intersects=aoi) if aoi else qs.none()

    return qs


# ── Catalog ──────────────────────────────────────────────────────────────


class SatelliteDatasetListAPIView(generics.ListAPIView):
    """GET /api/satellite/datasets/ — the catalog. Global, not org-scoped.

    Filters: ?verified=true, ?scale=SITE|REGIONAL, ?include_inactive=true.
    Inactive datasets are hidden by default — is_active exists so a product
    can be retired without deleting the rows that reference it.
    """

    serializer_class = SatelliteDatasetSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None  # ten rows; paginating it would only add ceremony

    def get_queryset(self):
        params = self.request.query_params
        qs = SatelliteDataset.objects.all()

        if params.get("include_inactive", "").lower() not in ("true", "1"):
            qs = qs.filter(is_active=True)

        verified = params.get("verified", "").lower()
        if verified in ("true", "1"):
            qs = qs.filter(is_verified=True)
        elif verified in ("false", "0"):
            qs = qs.filter(is_verified=False)

        scale = params.get("scale")
        if scale:
            qs = qs.filter(scale=scale.upper())

        return qs.order_by("scale", "resolution_m", "code")


class SatelliteDatasetDetailAPIView(generics.RetrieveAPIView):
    """GET /api/satellite/datasets/<id>/"""

    serializer_class = SatelliteDatasetSerializer
    permission_classes = (permissions.IsAuthenticated,)
    queryset = SatelliteDataset.objects.all()


# ── Queries ──────────────────────────────────────────────────────────────


class SatelliteQueryListAPIView(generics.ListAPIView):
    """GET /api/satellite/queries/ — org-scoped, newest first.

    Filters: ?dataset=<code>, ?status=COMPLETE|EMPTY|FAILED|...
    """

    serializer_class = SatelliteQuerySerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = _org_queries(self.request.user)
        params = self.request.query_params

        dataset_code = params.get("dataset")
        if dataset_code:
            qs = qs.filter(dataset__code=dataset_code)

        status_filter = params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        return qs.order_by("-created_at")


class SatelliteQueryDetailAPIView(generics.RetrieveAPIView):
    """GET /api/satellite/queries/<id>/ — query plus its scenes in one call.

    Scoping lives in get_queryset, not in a permission check on the object:
    another tenant's query 404s rather than 403s, which leaks nothing about
    whether that id exists.
    """

    serializer_class = SatelliteQueryDetailSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return _org_queries(self.request.user).prefetch_related("images__dataset")


# ── Images ───────────────────────────────────────────────────────────────


class SatelliteImageListAPIView(generics.ListAPIView):
    """GET /api/satellite/images/ — org-scoped, newest acquisition first.

    Filters: ?dataset=<code>, ?query=<id>, ?date_start, ?date_end,
             ?bbox=west,south,east,north
    """

    serializer_class = SatelliteImageSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = _org_images(self.request.user)
        qs = _filter_images(qs, self.request.query_params)
        return qs.order_by("-acquisition_date")


class SatelliteImageDetailAPIView(generics.RetrieveAPIView):
    """GET /api/satellite/images/<id>/"""

    serializer_class = SatelliteImageSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return _org_images(self.request.user)


# ── Coverage ─────────────────────────────────────────────────────────────


class SatelliteCoverageAPIView(generics.GenericAPIView):
    """GET /api/satellite/coverage/ — footprints as a GeoJSON FeatureCollection.

    The direct analogue of /api/map-data/, and what FieldMap consumes. Without
    it every client would have to rebuild polygons from the images list's
    bboxes, which is the kind of duplication that drifts.

    Accepts the same filters as the images list.
    """

    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        qs = _org_images(self.request.user)
        qs = _filter_images(qs, self.request.query_params)
        return qs.order_by("-acquisition_date")[:MAX_COVERAGE_FEATURES]

    def get(self, request, *args, **kwargs):
        features = []
        for image in self.get_queryset():
            features.append({
                "type": "Feature",
                # The footprint is what is on disk, not what Earth Engine
                # reported for the scene — fetch_scenes reads it off the
                # raster. Rendering the scene extent here would draw a box
                # a thousand times too large.
                "geometry": json.loads(image.geometry.geojson),
                "properties": {
                    "id": image.id,
                    "query_id": image.query_id,
                    "dataset": image.dataset.code,
                    "dataset_name": image.dataset.name,
                    "resolution_m": image.dataset.resolution_m,
                    # SITE vs REGIONAL rides along here too, so a map cannot
                    # draw an 11 km covariate as if it measured one site.
                    "scale": image.dataset.scale,
                    "acquisition_date": image.acquisition_date.isoformat(),
                    "cloud_cover_pct": image.cloud_cover_pct,
                    "has_cog": image.has_cog,
                },
            })
        return Response(
            {"type": "FeatureCollection", "features": features},
            status=status.HTTP_200_OK,
        )
class SatelliteImageRenderAPIView(views.APIView):
    """GET /api/satellite/images/<pk>/render/?layer=<key>

    Serves a PNG rendered from OUR COG, cached beside it. See render.py for
    why not GEE tile URLs and why not a tile server.

    Tenancy is re-checked HERE, per request. cog_path is deliberately not
    serialized (ADR-0012 §6) because DEBUG serves MEDIA_URL with no auth, so
    a leaked path would make every org-scoped queryset bypassable by string
    concatenation. That protection is worth nothing if the endpoint that
    turns an id into pixels does not scope the lookup itself.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        # Scoped queryset, not SatelliteImage.objects — a 404 for another
        # tenant's id, never a 403, because 403 confirms the row exists.
        image = get_object_or_404(_org_images(request.user), pk=pk)

        layer_key = request.query_params.get("layer", "").strip()
        if not layer_key:
            return Response(
                {
                    "detail": "A ?layer= parameter is required.",
                    "available": sorted(
                        l.key for l in render.layers_for(image.dataset.code)
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            layer = render.get_layer(image.dataset.code, layer_key)
        except render.UnknownLayer as exc:
            # 404, and never a fallback to another dataset's recipe. Falling
            # back is how an S2 index gets computed over an L9 scene, which
            # renders perfectly and is wrong.
            return Response(
                {"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND
            )

        if not image.has_cog:
            return Response(
                {
                    "detail": (
                        "This scene has a catalog row but no COG on disk. "
                        "Run fetch_scenes for it."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            absolute = cog.absolute_cog_path(image.cog_path)
        except cog.CogError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_409_CONFLICT
            )

        if not absolute.exists():
            return Response(
                {"detail": f"COG missing on disk: {image.cog_path}"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            png = render.cached_or_render(absolute, layer)
        except render.MissingBands as exc:
            # 409, not 500: the row and the file are both fine, they just do
            # not carry what this layer needs. Naming the band is the whole
            # value of the message.
            return Response(
                {"detail": str(exc)}, status=status.HTTP_409_CONFLICT
            )

        response = FileResponse(open(png, "rb"), content_type="image/png")
        # private: this is tenant data behind auth, never shared-cacheable.
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Ranger-Layer"] = layer.key
        return response


# ─── RANGER V3 END: satellite api views ───