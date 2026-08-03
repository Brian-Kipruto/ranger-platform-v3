# ─── RANGER V3 START: F10.1 sensorlog geometry required ───
"""
Step 3 of 3 (contract): make `location` NOT NULL.

The guard runs before the AlterField. If any row is still NULL the migration
aborts with a clear message instead of surfacing a raw IntegrityError from
Postgres.
"""
import django.contrib.gis.db.models.fields
from django.db import migrations


def guard(apps, schema_editor):
    SensorLog = apps.get_model("core", "SensorLog")
    missing = SensorLog.objects.filter(location__isnull=True).count()
    if missing:
        raise RuntimeError(
            f"{missing} SensorLog rows have NULL location. Run 0005 first, or "
            f"investigate rows added between 0005 and now."
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_backfill_sensorlog_location"),
    ]

    operations = [
        migrations.RunPython(guard, noop),
        migrations.AlterField(
            model_name="sensorlog",
            name="location",
            field=django.contrib.gis.db.models.fields.PointField(
                srid=4326,
                help_text="WGS84 position of this reading. Source of truth for "
                          "coordinates; latitude/longitude are derived from it.",
            ),
        ),
    ]
# ─── RANGER V3 END: F10.1 sensorlog geometry required ───
