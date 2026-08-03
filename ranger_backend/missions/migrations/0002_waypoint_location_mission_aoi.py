# ─── RANGER V3 START: F10.1 missions geometry ───
"""
Step 1 of 3 (expand) for missions, plus the brand-new Mission AOI.

Two different things in one migration, deliberately:

  * Waypoint.location   — NULLABLE for now; 0003 backfills, 0004 tightens.
  * Mission.area_of_interest — NEW field, permanently nullable. Nothing to
    backfill from: Mission never had geometry. This is what F10.2's
    SatelliteQuery scopes scene retrieval against.

Depends on core.0003_enable_postgis so the extension is guaranteed present
before any geometry column is created, regardless of how Django happens to
order the app migration graph.
"""
import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("missions", "0001_initial"),
        ("core", "0003_enable_postgis"),
    ]

    operations = [
        migrations.AddField(
            model_name="waypoint",
            name="location",
            field=django.contrib.gis.db.models.fields.PointField(
                srid=4326,
                null=True,
                blank=True,
                help_text="WGS84 target position. Source of truth for coordinates.",
            ),
        ),
        migrations.AddField(
            model_name="mission",
            name="area_of_interest",
            field=django.contrib.gis.db.models.fields.PolygonField(
                srid=4326,
                null=True,
                blank=True,
                help_text="Optional WGS84 survey boundary. Scopes satellite scene "
                          "retrieval and ground-truth correlation (F10.2+).",
            ),
        ),
    ]
# ─── RANGER V3 END: F10.1 missions geometry ───
