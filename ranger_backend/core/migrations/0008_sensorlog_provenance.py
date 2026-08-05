# ─── RANGER V3 START: F10.2 sensorlog provenance ───
"""Adds `source` + `provenance_note` to SensorLog (F10.2 CP2).

Pulled forward from F08, where the source flag was originally scoped. It has
to land BEFORE any Marsabit data is seeded (CP3) and long before F10.4 writes
ValidationRecords: retrofitting provenance onto rows that already have
validation results attached means deciding, after the fact, what each row
was — which is exactly the guess this field exists to prevent.

Existing rows are all from run_simulation, so the backfill is unconditional:
everything currently in the table is SIMULATED. The field default matches, so
a row written by code that forgot to set it degrades to the least
authoritative label rather than silently claiming to be a measurement.
"""
from django.db import migrations, models


def backfill_simulated(apps, schema_editor):
    SensorLog = apps.get_model("core", "SensorLog")
    updated = SensorLog.objects.update(source="simulated")
    print(f"\n    labelled {updated} existing SensorLog rows as 'simulated'")


def reverse_noop(apps, schema_editor):
    # Nothing to undo: the columns themselves are removed on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_drop_sensorlog_floats"),
    ]

    operations = [
        migrations.AddField(
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
                max_length=10,
                help_text="Provenance of this reading. Drives the honesty of every "
                          "downstream validation claim.",
            ),
        ),
        migrations.AddField(
            model_name="sensorlog",
            name="provenance_note",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                help_text="Citation or derivation, e.g. 'KNRA Marsabit survey 2026, "
                          "Table 3.2, sample Gamura-1'. Required in practice for "
                          "REPORTED and MODELLED rows.",
            ),
        ),
        migrations.RunPython(backfill_simulated, reverse_noop),
    ]
# ─── RANGER V3 END: F10.2 sensorlog provenance ───
