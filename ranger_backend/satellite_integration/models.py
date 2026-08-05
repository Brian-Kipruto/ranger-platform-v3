# ─── RANGER V3 START: satellite integration models ───
"""
satellite_integration — catalog, queries, and retrieved scenes (F10.2).

Three models, one per stage of the pipeline:

    SatelliteDataset   the catalog. What we CAN retrieve. Global, no tenant.
    SatelliteQuery     a request. Org + AOI + date range + dataset.
    SatelliteImage     a result. One scene, its footprint, its COG on disk.

Tenancy (ADR-0006 context): note the deliberate asymmetry.
  * SatelliteDataset has NO organization FK. Sentinel-2 is Sentinel-2 for
    everyone; the catalog is global reference data, like SensorType.
  * SatelliteQuery carries `organization` DIRECTLY — the Mission pattern, not
    the SensorLog-through-Robot pattern. A query is initiated by an org, not
    by a robot, and satellite retrieval costs real quota, so the org that
    spent it owns the record.
  * SatelliteImage inherits its tenant THROUGH its query (see .organization).

Geometry is PostGIS, SRID 4326, per ADR-0011. Build polygons with
core.geo.polygon_from_bbox — never a bare Polygon() — so bbox argument order
is enforced in one place.
"""
from django.contrib.gis.db import models as gis_models
from django.db import models


class SatelliteDataset(models.Model):
    """A satellite data product we know how to retrieve.

    Seeded by `manage.py seed_datasets`, not created by users. `is_verified`
    means we have actually pulled a scene from it — the mockup's DATA
    PROVIDERS panel distinguishes "catalogued" from "connected", and this is
    the field behind that.
    """

    class Provider(models.TextChoices):
        ESA = "ESA", "European Space Agency"
        NASA = "NASA", "NASA"
        USGS = "USGS", "USGS"
        UCSB = "UCSB", "UC Santa Barbara"
        ECMWF = "ECMWF", "ECMWF"

    class Scale(models.TextChoices):
        # Drives what a dataset can honestly be used FOR. The Marsabit survey
        # sites are 100-300 m across:
        #   SITE     resolution fine enough to resolve a single site
        #   REGIONAL one pixel covers a whole site -> a covariate, not a
        #            per-site measurement (SMAP 9 km, CHIRPS 5 km, ERA5)
        SITE = "SITE", "Per-site (resolution < site size)"
        REGIONAL = "REGIONAL", "Regional covariate (pixel > site)"

    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Short handle used on the CLI, e.g. 's2', 'l5', 'smap'.",
    )
    provider = models.CharField(max_length=10, choices=Provider.choices)
    gee_collection_id = models.CharField(
        max_length=200,
        unique=True,
        help_text="Earth Engine collection ID, e.g. COPERNICUS/S2_SR_HARMONIZED.",
    )

    resolution_m = models.PositiveIntegerField(help_text="Nominal pixel size in metres.")
    temporal_resolution_days = models.FloatField(
        help_text="Nominal revisit interval in days."
    )
    scale = models.CharField(max_length=10, choices=Scale.choices, default=Scale.SITE)

    bands = models.JSONField(
        default=list,
        blank=True,
        help_text="Band names available, as a list of strings.",
    )

    # Archive coverage. archive_start is load-bearing for the F10.2 narrative:
    # Landsat 5 opens in 1984, and the Laga Balal wells were drilled Dec 1985,
    # so the archive predates the disturbance we're looking for.
    archive_start = models.DateField(
        null=True, blank=True, help_text="First acquisition available."
    )
    archive_end = models.DateField(
        null=True, blank=True, help_text="Last acquisition; null = ongoing."
    )

    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="True once a real scene has been retrieved from this "
                  "collection. Drives the DATA PROVIDERS connection status.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "satellite dataset"

    def __str__(self) -> str:
        return f"{self.name} ({self.resolution_m} m)"


class SatelliteQuery(models.Model):
    """One request for scenes over an AOI and date range."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        COMPLETE = "COMPLETE", "Complete"
        EMPTY = "EMPTY", "Complete, no scenes matched"
        FAILED = "FAILED", "Failed"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="satellite_queries",
    )
    dataset = models.ForeignKey(
        SatelliteDataset,
        on_delete=models.PROTECT,
        related_name="queries",
    )
    # Optional link to the mission whose area_of_interest this queries. Set
    # when the AOI came from a mission; null for ad-hoc bboxes.
    mission = models.ForeignKey(
        "missions.Mission",
        on_delete=models.SET_NULL,
        related_name="satellite_queries",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        related_name="satellite_queries_created",
        null=True,
        blank=True,
    )

    # The AOI actually queried. Copied rather than referenced through mission,
    # so editing a mission's AOI later doesn't silently rewrite the history of
    # what was already retrieved.
    geometry = gis_models.PolygonField(
        srid=4326,
        help_text="WGS84 area of interest queried. Build with "
                  "core.geo.polygon_from_bbox.",
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Human handle, e.g. 'forole-s2-2026'.",
    )

    start_date = models.DateField()
    end_date = models.DateField()
    max_cloud_pct = models.FloatField(
        null=True,
        blank=True,
        help_text="Cloud cover ceiling applied. Null = no cloud filter "
                  "(radar and reanalysis products have no cloud property).",
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    scene_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "satellite queries"

    def __str__(self) -> str:
        return (
            f"{self.dataset.code} {self.start_date}..{self.end_date} "
            f"[{self.status}]"
        )


class SatelliteImage(models.Model):
    """One retrieved scene: metadata, footprint, and the COG on disk."""

    query = models.ForeignKey(
        SatelliteQuery,
        on_delete=models.CASCADE,
        related_name="images",
    )
    # Denormalized from query.dataset so scene lookups don't need a join
    # through query. Kept consistent in save().
    dataset = models.ForeignKey(
        SatelliteDataset,
        on_delete=models.PROTECT,
        related_name="images",
    )

    # THE durable identifier. Tile URLs expire; GEE asset IDs do not, so this
    # is what any regeneration works from.
    gee_asset_id = models.CharField(max_length=300, db_index=True)

    acquisition_date = models.DateTimeField(db_index=True)
    cloud_cover_pct = models.FloatField(null=True, blank=True)

    # Scene footprint, or the AOI-clipped extent once downloaded. GiST-indexed
    # (spatial_index defaults True) so intersects/within use an index scan.
    geometry = gis_models.PolygonField(
        srid=4326,
        help_text="WGS84 footprint of the retrieved raster.",
    )

    # Local COG, written by CP5. Relative to MEDIA_ROOT/satellite/.
    cog_path = models.CharField(max_length=500, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)

    # A GEE tile URL is a CACHE, never a source of truth: Google expires them
    # after a few days. Anything reading this MUST check tiles_expire_at and
    # regenerate from gee_asset_id when stale — a demo that depends on a
    # cached tile URL will fail silently days later.
    tile_url = models.URLField(max_length=1000, blank=True, default="")
    tiles_expire_at = models.DateTimeField(null=True, blank=True)

    bands = models.JSONField(default=list, blank=True)
    properties = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw GEE scene properties, kept verbatim for provenance.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acquisition_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["query", "gee_asset_id"],
                name="unique_asset_per_query",
            )
        ]

    def __str__(self) -> str:
        return f"{self.gee_asset_id} @ {self.acquisition_date:%Y-%m-%d}"

    @property
    def organization(self):
        """Tenant, inherited through the query (no own org FK)."""
        return self.query.organization

    @property
    def has_cog(self) -> bool:
        return bool(self.cog_path)

    def tiles_are_stale(self, now=None) -> bool:
        """True if the cached tile URL is missing or past its expiry."""
        from django.utils import timezone

        if not self.tile_url or self.tiles_expire_at is None:
            return True
        return (now or timezone.now()) >= self.tiles_expire_at

    def save(self, *args, **kwargs):
        # Keep the denormalized dataset honest rather than trusting callers.
        if self.query_id and not self.dataset_id:
            self.dataset_id = self.query.dataset_id
        super().save(*args, **kwargs)
# ─── RANGER V3 END: satellite integration models ───
