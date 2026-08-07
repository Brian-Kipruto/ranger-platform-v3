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

    def test_map_data_properties_include_provenance_note(
        self, authed_client, sensor_log_at, robot
    ):
        """F10.3 CP0. The tier says MODELLED; the note says modelled from WHAT.

        The Data Explorer quotes this verbatim in its all-modelled banner, so
        a map payload that carries the label but drops the citation produces a
        banner that warns without evidencing — which is a disclaimer, not
        provenance. The serializer and CSV have carried both since F10.2 CP2;
        this closes the third path out of the backend.
        """
        log = sensor_log_at(3.7167, 37.9672, robot=robot)
        log.source = SensorLog.Source.MODELLED
        log.provenance_note = KNRA_CITATION
        log.save(update_fields=["source", "provenance_note"])

        response = authed_client.get(reverse("map-data"))
        props = response.data["features"][0]["properties"]
        assert props["source"] == "modelled"
        assert props["provenance_note"] == KNRA_CITATION

    def test_all_three_backend_paths_agree_on_provenance(
        self, authed_client, sensor_log_at, robot
    ):
        """Serializer, CSV and map payload must not drift apart.

        Three independent code paths emit provenance. Each has its own test
        above; this one asserts they agree, because the failure that actually
        bites is not "one path is broken" but "two paths disagree and the
        screen believes the wrong one".
        """
        log = sensor_log_at(3.7167, 37.9672, robot=robot)
        log.source = SensorLog.Source.REPORTED
        log.provenance_note = KNRA_CITATION
        log.save(update_fields=["source", "provenance_note"])

        serialized = DataLogSerializer(SensorLog.objects.get(pk=log.pk)).data

        csv_rows = list(csv.DictReader(io.StringIO(
            authed_client.get(reverse("data-log-export-csv")).content.decode()
        )))
        map_props = authed_client.get(
            reverse("map-data")
        ).data["features"][0]["properties"]

        assert (
            serialized["source"]
            == csv_rows[0]["source"]
            == map_props["source"]
            == "reported"
        )
        assert (
            serialized["provenance_note"]
            == csv_rows[0]["provenance_note"]
            == map_props["provenance_note"]
            == KNRA_CITATION
        )


@pytest.mark.django_db
class TestMapProvenanceSummary:
    """F10.3 CP0.5 — the summary describes the FILTERED set, not the sample.

    The map payload is capped at MAX_CHART_POINTS. Before this block existed,
    the console derived its provenance banner from the capped features array,
    so it announced "ALL 5,000 POINTS IN THIS SET ARE MODELLED" directly above
    a record count of 12,081 — and quoted ONE arbitrary feature's citation as
    though it covered every site. These tests exist so the numbers on screen
    are numbers something actually counted.
    """

    def test_total_counts_the_uncapped_set(
        self, authed_client, sensor_log_at, robot, settings
    ):
        from core import views

        for i in range(6):
            log = sensor_log_at(3.71 + i * 0.001, 37.96, robot=robot)
            log.source = SensorLog.Source.MODELLED
            log.save(update_fields=["source"])

        # Cap below the row count so the sample is genuinely smaller.
        original = views.MAX_CHART_POINTS
        views.MAX_CHART_POINTS = 3
        try:
            data = authed_client.get(reverse("map-data")).data
        finally:
            views.MAX_CHART_POINTS = original

        assert len(data["features"]) == 3
        assert data["provenance"]["total"] == 6
        assert data["provenance"]["returned"] == 3
        assert data["provenance"]["truncated"] is True
        assert data["provenance"]["by_source"]["modelled"] == 6

    def test_not_truncated_when_everything_fits(
        self, authed_client, sensor_log_at, robot
    ):
        sensor_log_at(3.71, 37.96, robot=robot)
        prov = authed_client.get(reverse("map-data")).data["provenance"]
        assert prov["truncated"] is False
        assert prov["returned"] == prov["total"] == 1

    def test_distinct_notes_are_all_returned(
        self, authed_client, sensor_log_at, robot
    ):
        """Several sites means several citations.

        The frontend needs to KNOW there are several, so it can decline to
        quote one of them as the citation for the whole set. A summary that
        collapsed this to a single string would hand the UI a wrong citation
        and no way to detect it.
        """
        for i, note in enumerate(["Table 3.1 (Boji)", "Table 3.1 (Forole)"]):
            log = sensor_log_at(3.71 + i * 0.001, 37.96, robot=robot)
            log.source = SensorLog.Source.MODELLED
            log.provenance_note = note
            log.save(update_fields=["source", "provenance_note"])

        prov = authed_client.get(reverse("map-data")).data["provenance"]
        assert sorted(prov["notes"]) == ["Table 3.1 (Boji)", "Table 3.1 (Forole)"]
        assert prov["notes_truncated"] is False

    def test_many_rows_sharing_one_note_collapse_to_one(
        self, authed_client, sensor_log_at, robot
    ):
        """The regression that the two-note test above could not catch.

        seed_marsabit writes ONE citation per site across every point in it,
        so a single-site filter must yield exactly one note and the banner
        must quote it. Chaining .distinct() onto a timestamp-ordered queryset
        instead returned one "distinct" note PER ROW — 1,819 Forole points
        came back as 1,819 citations and the banner said "12+ distinct
        citations" where it should have cited Table 3.1 directly.

        The earlier test used two rows with two different notes, where the
        correct and incorrect answers are both 2. This one uses many rows and
        one note, where they differ.
        """
        shared = "Modelled from KNRA Marsabit survey, Table 3.1 (Forole)"
        for i in range(8):
            log = sensor_log_at(3.71 + i * 0.001, 37.96, robot=robot)
            log.source = SensorLog.Source.MODELLED
            log.provenance_note = shared
            log.save(update_fields=["source", "provenance_note"])

        prov = authed_client.get(reverse("map-data")).data["provenance"]
        assert prov["total"] == 8
        assert prov["notes"] == [shared]
        assert prov["notes_truncated"] is False

    def test_blank_notes_are_excluded(self, authed_client, sensor_log_at, robot):
        """An empty string is not a citation; it must not pad the count the
        banner uses to decide whether it can quote one."""
        sensor_log_at(3.71, 37.96, robot=robot)  # default source, blank note
        prov = authed_client.get(reverse("map-data")).data["provenance"]
        assert prov["notes"] == []

    def test_summary_respects_filters(
        self, authed_client, sensor_log_at, robot, mission
    ):
        """The summary must describe the FILTERED set.

        If it counted the whole org regardless of filters, every narrowing
        would still read 12,081 and the banner would be a constant rather
        than a readout — which is indistinguishable from a broken one.
        """
        a = sensor_log_at(3.71, 37.96, robot=robot, mission=mission)
        a.source = SensorLog.Source.MODELLED
        a.save(update_fields=["source"])
        b = sensor_log_at(3.72, 37.97, robot=robot)
        b.source = SensorLog.Source.REPORTED
        b.save(update_fields=["source"])

        prov = authed_client.get(
            reverse("map-data"), {"mission_id": mission.id}
        ).data["provenance"]
        assert prov["total"] == 1
        assert prov["by_source"] == {"modelled": 1}

    def test_summary_is_org_scoped(
        self, authed_client, sensor_log_at, robot, other_robot
    ):
        """Tenancy holds on the aggregate too.

        An aggregate that skipped the org filter would put another tenant's
        row count on this tenant's screen — a leak that shows up as a wrong
        number rather than as an error, so nothing else would catch it.
        """
        sensor_log_at(3.71, 37.96, robot=robot)
        sensor_log_at(3.72, 37.97, robot=other_robot)

        prov = authed_client.get(reverse("map-data")).data["provenance"]
        assert prov["total"] == 1
# ─── RANGER V3 END: provenance tests ───