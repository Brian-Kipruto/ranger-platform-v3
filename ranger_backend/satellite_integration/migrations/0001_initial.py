# ─── RANGER V3 START: satellite integration initial ───
"""Initial schema for satellite_integration (F10.2 CP1).

Depends on core.0003_enable_postgis so the PostGIS extension is guaranteed
present before any geometry column is created — same discipline as F10.1's
missions.0002, and not something to leave to Django's graph resolution.
"""
import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("missions", "0005_drop_waypoint_floats"),
        ("core", "0003_enable_postgis"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SatelliteDataset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("code", models.SlugField(
                    max_length=50, unique=True,
                    help_text="Short handle used on the CLI, e.g. 's2', 'l5', 'smap'.")),
                ("provider", models.CharField(choices=[
                    ("ESA", "European Space Agency"), ("NASA", "NASA"),
                    ("USGS", "USGS"), ("UCSB", "UC Santa Barbara"),
                    ("ECMWF", "ECMWF")], max_length=10)),
                ("gee_collection_id", models.CharField(
                    max_length=200, unique=True,
                    help_text="Earth Engine collection ID, e.g. COPERNICUS/S2_SR_HARMONIZED.")),
                ("resolution_m", models.PositiveIntegerField(
                    help_text="Nominal pixel size in metres.")),
                ("temporal_resolution_days", models.FloatField(
                    help_text="Nominal revisit interval in days.")),
                ("scale", models.CharField(choices=[
                    ("SITE", "Per-site (resolution < site size)"),
                    ("REGIONAL", "Regional covariate (pixel > site)")],
                    default="SITE", max_length=10)),
                ("bands", models.JSONField(
                    blank=True, default=list,
                    help_text="Band names available, as a list of strings.")),
                ("archive_start", models.DateField(
                    blank=True, null=True, help_text="First acquisition available.")),
                ("archive_end", models.DateField(
                    blank=True, null=True,
                    help_text="Last acquisition; null = ongoing.")),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("is_verified", models.BooleanField(
                    default=False,
                    help_text="True once a real scene has been retrieved from this "
                              "collection. Drives the DATA PROVIDERS connection status.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "satellite dataset",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="SatelliteQuery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("geometry", django.contrib.gis.db.models.fields.PolygonField(
                    srid=4326,
                    help_text="WGS84 area of interest queried. Build with "
                              "core.geo.polygon_from_bbox.")),
                ("label", models.CharField(
                    blank=True, default="", max_length=200,
                    help_text="Human handle, e.g. 'forole-s2-2026'.")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("max_cloud_pct", models.FloatField(
                    blank=True, null=True,
                    help_text="Cloud cover ceiling applied. Null = no cloud filter "
                              "(radar and reanalysis products have no cloud property).")),
                ("status", models.CharField(choices=[
                    ("PENDING", "Pending"), ("RUNNING", "Running"),
                    ("COMPLETE", "Complete"),
                    ("EMPTY", "Complete, no scenes matched"),
                    ("FAILED", "Failed")],
                    db_index=True, default="PENDING", max_length=10)),
                ("scene_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="satellite_queries_created",
                    to=settings.AUTH_USER_MODEL)),
                ("dataset", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="queries",
                    to="satellite_integration.satellitedataset")),
                ("mission", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="satellite_queries", to="missions.mission")),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="satellite_queries", to="accounts.organization")),
            ],
            options={
                "verbose_name_plural": "satellite queries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SatelliteImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("gee_asset_id", models.CharField(db_index=True, max_length=300)),
                ("acquisition_date", models.DateTimeField(db_index=True)),
                ("cloud_cover_pct", models.FloatField(blank=True, null=True)),
                ("geometry", django.contrib.gis.db.models.fields.PolygonField(
                    srid=4326,
                    help_text="WGS84 footprint of the retrieved raster.")),
                ("cog_path", models.CharField(blank=True, default="", max_length=500)),
                ("size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("downloaded_at", models.DateTimeField(blank=True, null=True)),
                ("tile_url", models.URLField(blank=True, default="", max_length=1000)),
                ("tiles_expire_at", models.DateTimeField(blank=True, null=True)),
                ("bands", models.JSONField(blank=True, default=list)),
                ("properties", models.JSONField(
                    blank=True, default=dict,
                    help_text="Raw GEE scene properties, kept verbatim for provenance.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dataset", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="images",
                    to="satellite_integration.satellitedataset")),
                ("query", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="images", to="satellite_integration.satellitequery")),
            ],
            options={
                "ordering": ["-acquisition_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="satelliteimage",
            constraint=models.UniqueConstraint(
                fields=("query", "gee_asset_id"), name="unique_asset_per_query"),
        ),
    ]
# ─── RANGER V3 END: satellite integration initial ───
