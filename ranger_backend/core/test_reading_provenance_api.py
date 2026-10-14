# ─── RANGER V3 START: 13-reading-source ───
"""Per-reading provenance out of the backend: serializer, CSV, map (F13 5d).

`source` labels the position. Every path that emits a reading value also emits
that reading's own source, and the map summary counts readings by their own
source — so a set of LIVE positions carrying SIMULATED radiation is visible as
such instead of reading as "all measured".
"""
import csv
import io

import pytest
from django.urls import reverse

from core.models import AirQualityLog, ImuBaroLog, RadiationLog, SensorLog
from core.serializers import DataLogSerializer

S = SensorLog.Source
pytestmark = pytest.mark.django_db


@pytest.fixture
def mixed_log(sensor_log_at, robot):
    """The Pass 5 row: live fix, simulated radiation, live PM, no IMU."""
    log = sensor_log_at(-1.2864, 36.8172, robot=robot)
    log.source = S.LIVE
    log.save(update_fields=["source"])
    RadiationLog.objects.create(sensor_log=log, radiation_value=31.0, source=S.SIMULATED)
    AirQualityLog.objects.create(sensor_log=log, pm25=12.5, pm10=20.0, source=S.LIVE)
    return log


def test_serializer_labels_each_reading(mixed_log):
    d = DataLogSerializer(SensorLog.objects.get(pk=mixed_log.pk)).data
    assert d["source"] == "live"
    assert (d["radiation_source"], d["air_quality_source"], d["imu_source"]) == \
        ("simulated", "live", None)


def test_csv_carries_the_reading_sources(authed_client, mixed_log):
    body = authed_client.get(reverse("data-log-export-csv")).content.decode()
    row = next(csv.DictReader(io.StringIO(body)))
    assert row["source"] == "live"
    assert row["radiation_source"] == "simulated"
    assert row["air_quality_source"] == "live"
    assert row["imu_source"] == ""  # absent reading -> empty cell, not a label


def test_map_properties_carry_the_reading_sources(authed_client, mixed_log):
    props = authed_client.get(reverse("map-data")).data["features"][0]["properties"]
    assert props["source"] == "live"
    assert props["radiation_source"] == "simulated"
    assert props["air_quality_source"] == "live"


def test_summary_flags_simulated_readings_on_live_positions(authed_client, mixed_log):
    """The case the old banner missed: every POSITION is live."""
    prov = authed_client.get(reverse("map-data")).data["provenance"]
    assert prov["by_source"] == {"live": 1}
    assert prov["readings"] == {
        "radiation": {"simulated": 1},
        "air_quality": {"live": 1},
        "imu_baro": {},
    }


def test_summary_reading_counts_respect_filters_and_tenancy(
    authed_client, mixed_log, sensor_log_at, other_robot, robot
):
    """Counts come from the user's filtered, org-scoped set only."""
    foreign = sensor_log_at(-1.29, 36.82, robot=other_robot)  # other org
    RadiationLog.objects.create(sensor_log=foreign, radiation_value=99.0, source=S.LIVE)
    ImuBaroLog.objects.create(sensor_log=foreign, yaw=10.0, source=S.LIVE)

    prov = authed_client.get(reverse("map-data")).data["provenance"]
    assert prov["readings"]["radiation"] == {"simulated": 1}
    assert prov["readings"]["imu_baro"] == {}

    # A robot filter that excludes the mixed row empties the counts too.
    prov = authed_client.get(reverse("map-data"), {"robot_id": robot.id + 999}).data["provenance"]
    assert prov["total"] == 0
    assert prov["readings"] == {"radiation": {}, "air_quality": {}, "imu_baro": {}}


def test_all_three_paths_agree_on_reading_sources(authed_client, mixed_log):
    ser = DataLogSerializer(SensorLog.objects.get(pk=mixed_log.pk)).data
    row = next(csv.DictReader(io.StringIO(
        authed_client.get(reverse("data-log-export-csv")).content.decode())))
    props = authed_client.get(reverse("map-data")).data["features"][0]["properties"]
    for key in ("radiation_source", "air_quality_source"):
        assert ser[key] == row[key] == props[key], key
# ─── RANGER V3 END: 13-reading-source ───
