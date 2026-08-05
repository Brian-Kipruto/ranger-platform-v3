# ─── RANGER V3 START: provenance tests ───
"""Provenance labelling on SensorLog (F10.2 CP2).

In its own module rather than appended to core/tests.py: the provenance
contract is what the whole dual-source claim rests on, and it should be
readable — and greppable — as one thing.

The point of these tests is not that a CharField stores a string. It is that
a label can never silently go missing, and that it survives every path out of
the system: serializer, CSV export, and map payload. An export that drops its
labels is precisely how modelled data becomes "the KNRA measurements" three
hops downstream.
"""
import csv
import io

import pytest
from django.urls import reverse

from core.models import SensorLog
from core.serializers import DataLogSerializer

KNRA_CITATION = "KNRA Marsabit survey 2026, Table 3.2, sample Gamura-1"


@pytest.mark.django_db
class TestProvenanceDefaults:

    def test_defaults_to_simulated_not_live(self, sensor_log_at):
        """The default must be the LEAST authoritative label.

        A row written by code that forgot to set `source` should under-claim,
        never over-claim. This assertion is the whole design in one line.
        """
        log = sensor_log_at(-1.2921, 36.8219)
        assert log.source == SensorLog.Source.SIMULATED
        assert log.source != SensorLog.Source.LIVE

    def test_source_is_never_null_or_blank(self, sensor_log_at):
        log = SensorLog.objects.get(pk=sensor_log_at(-1.29, 36.82).pk)
        assert log.source

    def test_is_measured_only_for_live_and_reported(self, sensor_log_at):
        log = sensor_log_at(-1.29, 36.82)

        for source, expected in [
            (SensorLog.Source.LIVE, True),
            (SensorLog.Source.REPORTED, True),
            (SensorLog.Source.MODELLED, False),
            (SensorLog.Source.SIMULATED, False),
        ]:
            log.source = source
            assert log.is_measured is expected, f"{source} -> {expected}"

    def test_provenance_note_carries_a_citation(self, sensor_log_at):
        log = sensor_log_at(3.7167, 37.9672)
        log.source = SensorLog.Source.REPORTED
        log.provenance_note = KNRA_CITATION
        log.save(update_fields=["source", "provenance_note"])

        fetched = SensorLog.objects.get(pk=log.pk)
        assert fetched.provenance_note == KNRA_CITATION
        assert fetched.is_measured is True

    def test_filterable_by_source(self, sensor_log_at):
        """Unlike lat/lon (properties since F10.1), source IS a real column,
        so it can be filtered — F10.4 needs to select measured rows only."""
        a = sensor_log_at(-1.29, 36.82)
        b = sensor_log_at(-1.30, 36.83)
        b.source = SensorLog.Source.MODELLED
        b.save(update_fields=["source"])

        assert SensorLog.objects.filter(source=SensorLog.Source.MODELLED).count() == 1
        measured = SensorLog.objects.filter(
            source__in=[SensorLog.Source.LIVE, SensorLog.Source.REPORTED]
        )
        assert measured.count() == 0
        assert a.pk not in measured.values_list("pk", flat=True)


@pytest.mark.django_db
class TestProvenanceSurvivesEveryExit:
    """Every path out of the system must carry the label."""

    def test_serializer_emits_source_and_note(self, sensor_log_at, robot):
        log = sensor_log_at(3.7167, 37.9672, robot=robot)
        log.source = SensorLog.Source.MODELLED
        log.provenance_note = "Modelled from KNRA Table 3.1 (Forole, n=1819)"
        log.save(update_fields=["source", "provenance_note"])

        data = DataLogSerializer(log).data
        assert data["source"] == "modelled"
        assert "KNRA" in data["provenance_note"]

    def test_csv_export_includes_provenance_columns(
        self, authed_client, sensor_log_at, robot
    ):
        log = sensor_log_at(3.7167, 37.9672, robot=robot, radiation=140.0)
        log.source = SensorLog.Source.REPORTED
        log.provenance_note = KNRA_CITATION
        log.save(update_fields=["source", "provenance_note"])

        response = authed_client.get(reverse("data-log-export-csv"))
        assert response.status_code == 200

        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        assert "source" in rows[0]
        assert rows[0]["source"] == "reported"
        assert rows[0]["provenance_note"] == KNRA_CITATION

    def test_map_data_properties_include_source(
        self, authed_client, sensor_log_at, robot
    ):
        """The map badges markers by provenance — without this the user cannot
        see which points are modelled without clicking each one."""
        log = sensor_log_at(3.7167, 37.9672, robot=robot)
        log.source = SensorLog.Source.MODELLED
        log.save(update_fields=["source"])

        response = authed_client.get(reverse("map-data"))
        assert response.data["features"][0]["properties"]["source"] == "modelled"
# ─── RANGER V3 END: provenance tests ───
