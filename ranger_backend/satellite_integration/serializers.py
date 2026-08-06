# ─── RANGER V3 START: satellite api serializers ───
"""
Read-only serializers for the satellite EO endpoints (F10.2 CP6).

Three shapes, one per model, with two rules that are not negotiable:

1. `cog_path` IS NEVER SERIALIZED. It is a filesystem path relative to
   MEDIA_ROOT, and a path is not a URL. Emitting it would invite a client to
   construct `/media/satellite/<org>/...` directly, which bypasses org
   scoping entirely — any authenticated user could read another tenant's
   rasters by guessing a path. Clients get `has_cog` and, from F10.3, a
   render endpoint that re-checks tenancy on every request.

2. `dataset.scale` RIDES ON EVERY IMAGE. SITE vs REGIONAL is what separates
   "Sentinel-2 resolves this 300 m site" from "one SMAP pixel covers the
   whole county", and the honesty discipline that governs SensorLog.source is
   worth nothing if it stops at the API boundary. A frontend that renders a
   REGIONAL product as a per-site measurement should have had to ignore a
   field to do it.

Geometry crosses as a plain `bbox` list — [west, south, east, north] — rather
than GeoJSON. It is what MapLibre's ImageSource wants for a raster overlay and
what a bounds check wants, and every footprint here is an axis-aligned clip
anyway. `/api/satellite/coverage/` serves real GeoJSON for the map layer.
"""
from rest_framework import serializers

from .models import SatelliteDataset, SatelliteImage, SatelliteQuery


def bbox_of(geometry) -> list[float] | None:
    """[west, south, east, north] in EPSG:4326, or None."""
    if geometry is None:
        return None
    return [round(v, 6) for v in geometry.extent]


class SatelliteDatasetSerializer(serializers.ModelSerializer):
    """The catalog. Global reference data — no tenant, like SensorType."""

    provider_label = serializers.CharField(source="get_provider_display", read_only=True)
    scale_label = serializers.CharField(source="get_scale_display", read_only=True)
    # True only once fetch_scenes has put a real scene on disk. This is the
    # field behind the mockup's DATA PROVIDERS connection status, and it means
    # something stronger than "the collection ID resolves" (which is all
    # check_gee proves).
    has_cloud_filter = serializers.SerializerMethodField()

    class Meta:
        model = SatelliteDataset
        fields = [
            "id",
            "code",
            "name",
            "provider",
            "provider_label",
            "gee_collection_id",
            "resolution_m",
            "temporal_resolution_days",
            "scale",
            "scale_label",
            "bands",
            "archive_start",
            "archive_end",
            "has_cloud_filter",
            "description",
            "is_active",
            "is_verified",
        ]
        read_only_fields = fields

    def get_has_cloud_filter(self, obj) -> bool:
        """Whether a cloud ceiling can be applied at all.

        Exposed as a boolean rather than the raw property name: the client has
        no use for "CLOUDY_PIXEL_PERCENTAGE", but it very much needs to know
        not to offer a cloud slider for radar.
        """
        return bool(obj.cloud_property)


class SatelliteImageSerializer(serializers.ModelSerializer):
    """One retrieved scene. Tenancy is inherited through its query."""

    dataset_code = serializers.CharField(source="dataset.code", read_only=True)
    dataset_name = serializers.CharField(source="dataset.name", read_only=True)
    provider = serializers.CharField(source="dataset.provider", read_only=True)
    resolution_m = serializers.IntegerField(source="dataset.resolution_m", read_only=True)
    # See rule 2 in the module docstring.
    scale = serializers.CharField(source="dataset.scale", read_only=True)

    bbox = serializers.SerializerMethodField()
    has_cog = serializers.ReadOnlyField()
    tiles_stale = serializers.SerializerMethodField()

    class Meta:
        model = SatelliteImage
        fields = [
            "id",
            "query",
            "dataset",
            "dataset_code",
            "dataset_name",
            "provider",
            "resolution_m",
            "scale",
            "gee_asset_id",
            "acquisition_date",
            "cloud_cover_pct",
            "bbox",
            "bands",
            "has_cog",
            "size_bytes",
            "downloaded_at",
            "tiles_stale",
            "properties",
            "created_at",
        ]
        read_only_fields = fields

    def get_bbox(self, obj) -> list[float] | None:
        return bbox_of(obj.geometry)

    def get_tiles_stale(self, obj) -> bool:
        """A cached GEE tile URL is never authoritative — see the model.

        Surfaced so a client can tell the difference between "no imagery" and
        "the cached link expired and needs regenerating from gee_asset_id".
        """
        return obj.tiles_are_stale()


class SatelliteQuerySerializer(serializers.ModelSerializer):
    """One retrieval request. Carries `organization` directly (Mission pattern)."""

    dataset_code = serializers.CharField(source="dataset.code", read_only=True)
    dataset_name = serializers.CharField(source="dataset.name", read_only=True)
    mission_name = serializers.CharField(
        source="mission.name", read_only=True, allow_null=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    aoi_bbox = serializers.SerializerMethodField()
    image_count = serializers.SerializerMethodField()

    class Meta:
        model = SatelliteQuery
        fields = [
            "id",
            "label",
            "dataset",
            "dataset_code",
            "dataset_name",
            "mission",
            "mission_name",
            "aoi_bbox",
            "start_date",
            "end_date",
            "max_cloud_pct",
            "status",
            "status_label",
            "scene_count",
            "image_count",
            "error_message",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_aoi_bbox(self, obj) -> list[float] | None:
        return bbox_of(obj.geometry)

    def get_image_count(self, obj) -> int:
        """Rows actually persisted, which is not always `scene_count`.

        `scene_count` is what the run reported; this is what survived. They
        diverge when an image is deleted, and a silent divergence between a
        stored count and reality is exactly the kind of thing worth being able
        to see from the outside.
        """
        return obj.images.count()


class SatelliteQueryDetailSerializer(SatelliteQuerySerializer):
    """Detail view: the query plus its scenes, so the client makes one call."""

    images = SatelliteImageSerializer(many=True, read_only=True)

    class Meta(SatelliteQuerySerializer.Meta):
        fields = SatelliteQuerySerializer.Meta.fields + ["images"]
        read_only_fields = fields
# ─── RANGER V3 END: satellite api serializers ───
