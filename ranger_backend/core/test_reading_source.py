# ─── RANGER V3 START: 13-reading-source ───
"""Per-reading provenance (F13 5-pre, ADR-0020).

One SensorLog row = one moment. Its `source` labels the position; each
reading labels itself. These tests pin the two properties the design rests on:

1. A reading never borrows the row's label. An unlabelled reading on a LIVE
   row is SIMULATED (ADR-0012's weakest default), and the column cannot be
   NULL, so there is no "inherit" path for a forgotten label to fall through.
2. Migration 0009 changes nothing about how existing data reads: every
   existing reading comes out with exactly its row's label.
"""
import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.geo import point_from_latlon
from core.models import AirQualityLog, ImuBaroLog, RadiationLog, SensorLog

S = SensorLog.Source

READINGS = {
    RadiationLog: {"radiation_value": 42.0},
    AirQualityLog: {"pm25": 18.5, "pm10": 30.1},
    ImuBaroLog: {"yaw": 91.0},
}


@pytest.fixture
def live_row(sensor_log_at):
    log = sensor_log_at(-1.2921, 36.8219)
    log.source = S.LIVE
    log.save(update_fields=["source"])
    return log


@pytest.mark.django_db
class TestReadingNeverBorrowsTheRowLabel:

    @pytest.mark.parametrize("model", list(READINGS), ids=lambda m: m.__name__)
    def test_unlabelled_reading_on_live_row_is_simulated(self, live_row, model):
        """The whole fork-7 decision in one assertion: no inherit."""
        reading = model.objects.create(sensor_log=live_row, **READINGS[model])
        reading.refresh_from_db()
        assert live_row.source == S.LIVE
        assert reading.source == S.SIMULATED
        assert not reading.is_measured

    def test_mixed_row_keeps_each_label(self, live_row):
        """Real fix + real PM + simulated radiation: the Pass 5 row."""
        RadiationLog.objects.create(sensor_log=live_row, radiation_value=40.0,
                                    source=S.SIMULATED)
        AirQualityLog.objects.create(sensor_log=live_row, pm25=12.0, source=S.LIVE)
        row = SensorLog.objects.get(pk=live_row.pk)
        assert row.source == S.LIVE
        assert row.radiation_data.source == S.SIMULATED
        assert row.air_quality_data.source == S.LIVE

    @pytest.mark.parametrize("model", list(READINGS), ids=lambda m: m.__name__)
    def test_source_column_is_not_nullable(self, live_row, model):
        """NULL would be an 'inherit' path in disguise. The DB refuses it."""
        model.objects.create(sensor_log=live_row, **READINGS[model])
        with pytest.raises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f"UPDATE {model._meta.db_table} SET source = NULL")

    def test_is_measured_only_for_live_and_reported(self, live_row):
        r = RadiationLog(sensor_log=live_row, radiation_value=1.0)
        for source, expected in [(S.LIVE, True), (S.REPORTED, True),
                                 (S.MODELLED, False), (S.SIMULATED, False)]:
            r.source = source
            assert r.is_measured is expected, source


BEFORE = [("core", "0008_sensorlog_provenance")]
AFTER = [("core", "0009_reading_source")]


@pytest.mark.django_db(transaction=True)
def test_migration_copies_each_rows_label_to_its_readings():
    """Existing data reads exactly as before 0009: reading label == row label."""
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(BEFORE)
        old = executor.loader.project_state(BEFORE).apps
        Org = old.get_model("accounts", "Organization")
        Robot = old.get_model("core", "Robot")
        Log = old.get_model("core", "SensorLog")
        Rad = old.get_model("core", "RadiationLog")
        Air = old.get_model("core", "AirQualityLog")
        Imu = old.get_model("core", "ImuBaroLog")

        org = Org.objects.create(name="Mig Org", slug="mig-org")
        bot = Robot.objects.create(organization=org, name="Mig", robot_id_str="MIG-001")
        expected = {}
        for i, src in enumerate(["live", "reported", "modelled", "simulated"]):
            log = Log.objects.create(
                robot=bot, timestamp=timezone.now(), source=src,
                location=point_from_latlon(lat=-1.29 + i * 0.001, lon=36.82),
            )
            Rad.objects.create(sensor_log=log, radiation_value=10.0 + i)
            Air.objects.create(sensor_log=log, pm25=5.0 + i)
            Imu.objects.create(sensor_log=log, yaw=float(i))
            expected[log.pk] = src
        bare = Log.objects.create(  # a row with no readings must be untouched
            robot=bot, timestamp=timezone.now(), source="reported",
            location=point_from_latlon(lat=-1.30, lon=36.83),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        new = executor.loader.project_state(AFTER).apps
        for name in ("RadiationLog", "AirQualityLog", "ImuBaroLog"):
            got = dict(new.get_model("core", name).objects
                       .values_list("sensor_log_id", "source"))
            assert got == expected, name
        NewLog = new.get_model("core", "SensorLog")
        assert dict(NewLog.objects.filter(pk__in=expected)
                    .values_list("pk", "source")) == expected
        assert NewLog.objects.get(pk=bare.pk).source == "reported"
    finally:
        MigrationExecutor(connection).migrate(leaves)
# ─── RANGER V3 END: 13-reading-source ───
