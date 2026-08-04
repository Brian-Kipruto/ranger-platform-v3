# ─── RANGER V3 START: F10.1 drop sensorlog floats ───
"""
CP4 — THE IRREVERSIBLE STEP.

Drops SensorLog.latitude and SensorLog.longitude. After this migration those
columns exist only in the pre-F10.1 pg_dump; `location` is the sole source of
truth and the model exposes `latitude`/`longitude` as read-only properties
derived from it.

The two db_index=True btrees go with the columns. Spatial access is served by
the GiST index on `location` added in 0004.

Reversibility: the RemoveField operations are technically reversible in
Django's graph (it can re-CREATE the columns) but the DATA is not — reversing
gives you two NOT NULL float columns with no values, which cannot be populated
from within the migration because the reverse of 0005 has already run in the
other direction. Treat this as a one-way door. Restore from pg_dump if needed.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_sensorlog_location_required"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sensorlog",
            name="latitude",
        ),
        migrations.RemoveField(
            model_name="sensorlog",
            name="longitude",
        ),
    ]
# ─── RANGER V3 END: F10.1 drop sensorlog floats ───
