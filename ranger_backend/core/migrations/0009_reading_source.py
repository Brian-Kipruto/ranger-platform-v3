# ─── RANGER V3 START: 13-reading-source ───
"""Per-reading `source` on RadiationLog / AirQualityLog / ImuBaroLog (F13, ADR-0020).

One SensorLog row can carry a real fix, real PM and simulated radiation. The
row's `source` now labels the position only; each reading gets its own.

AddField fills existing readings with the weakest default ('simulated'); the
backfill then copies each reading's PARENT row label, so every existing
reading reads exactly as it did before this migration (it was labelled by its
row). Rows themselves are untouched. One transaction on Postgres: there is no
window where a reading carries the default instead of its row's label.

No "null = inherit": a reading written later without a label must
under-claim as 'simulated', never pick up 'live' from the GPS fix.
"""
from django.db import migrations, models

READING_MODELS = ("RadiationLog", "AirQualityLog", "ImuBaroLog")
SOURCES = ("live", "reported", "modelled", "simulated")


def copy_row_source_to_readings(apps, schema_editor):
    for name in READING_MODELS:
        Model = apps.get_model("core", name)
        total = 0
        for src in SOURCES:
            total += Model.objects.filter(sensor_log__source=src).update(source=src)
        print(f"\n    {name}: {total} readings labelled from their row", end="")


def reverse_noop(apps, schema_editor):
    # The columns are dropped on reverse; nothing else to undo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_sensorlog_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="airqualitylog",
            name="source",
            field=models.CharField(
                choices=[
                    ("live", "Live sensor"),
                    ("reported", "Reported measurement"),
                    ("modelled", "Modelled from published statistics"),
                    ("simulated", "Simulated"),
                ],
                default="simulated",
                help_text="Provenance of this reading, independent of the row's position provenance.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="imubarolog",
            name="source",
            field=models.CharField(
                choices=[
                    ("live", "Live sensor"),
                    ("reported", "Reported measurement"),
                    ("modelled", "Modelled from published statistics"),
                    ("simulated", "Simulated"),
                ],
                default="simulated",
                help_text="Provenance of this reading, independent of the row's position provenance.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="radiationlog",
            name="source",
            field=models.CharField(
                choices=[
                    ("live", "Live sensor"),
                    ("reported", "Reported measurement"),
                    ("modelled", "Modelled from published statistics"),
                    ("simulated", "Simulated"),
                ],
                default="simulated",
                help_text="Provenance of this reading, independent of the row's position provenance.",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sensorlog",
            name="source",
            field=models.CharField(
                choices=[
                    ("live", "Live sensor"),
                    ("reported", "Reported measurement"),
                    ("modelled", "Modelled from published statistics"),
                    ("simulated", "Simulated"),
                ],
                db_index=True,
                default="simulated",
                help_text="Provenance of this row's position (the fix). Readings carry their own source (ADR-0020).",
                max_length=10,
            ),
        ),
        migrations.RunPython(copy_row_source_to_readings, reverse_noop),
    ]
# ─── RANGER V3 END: 13-reading-source ───
