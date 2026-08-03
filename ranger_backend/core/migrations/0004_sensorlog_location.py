# ─── RANGER V3 START: F10.1 sensorlog geometry ───
"""
Step 1 of 3 (expand): add the geometry column, NULLABLE.

Nullable because the table has rows. A non-null AddField on a populated table
either fails or demands a default, and there is no sensible default for a
position. 0005 backfills; 0006 tightens to NOT NULL.
"""
import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_enable_postgis"),
    ]

    operations = [
        migrations.AddField(
            model_name="sensorlog",
            name="location",
            field=django.contrib.gis.db.models.fields.PointField(
                srid=4326,
                null=True,
                blank=True,
                help_text="WGS84 position of this reading. Source of truth for "
                          "coordinates; latitude/longitude are derived from it.",
            ),
        ),
    ]
# ─── RANGER V3 END: F10.1 sensorlog geometry ───
