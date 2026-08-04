# ─── RANGER V3 START: core geo + contract tests ───
"""
Tests for the F10.1 PostGIS foundation and the API contract it must not break.

What these protect, and why each one exists:

1. Geometry round-trip — `location` is the source of truth and latitude/
   longitude are properties over it. If that shim breaks, every consumer
   breaks silently.

2. Coordinate ORDER — promoted here from a one-off migration assertion. A
   migration assertion protects one run; a test protects every future write
   path (the ROS bridge in F08/F09, satellite ingestion in F10.2). PostGIS
   Point is (x, y) = (lon, lat) while humans say "lat, lon", and an inverted
   Kenyan coordinate is still a VALID coordinate — it lands in the Indian
   Ocean and renders happily on a map. Nothing catches it but this.

3. CSV header stability — people have downloaded exports. The column list is
   a contract with files already on disk.

4. Null-safe serialization — the F05 regression this codebase already paid
   for once: a log whose robot has no imu_baro must still serialize.

5. Spatial queries — the actual reason PostGIS is here at all (F10.4).

6. Tenancy (ADR-0006) — org scoping runs through robot__organization and must
   survive the schema change.
"""
import csv
import io

import pytest
from django.urls import reverse

from core.geo import KENYA_BBOX, point_from_latlon, polygon_from_bbox
from core.models import SensorLog
from core.serializers import DataLogSerializer

# The exact CSV header from core.views.data_log_export_csv. Duplicated here on
# purpose: if someone edits the view's fieldnames, this test fails and forces
# a deliberate decision rather than a silent break.
EXPECTED_CSV_HEADER = [
    "id", "robot_id", "robot_id_str", "robot_name", "mission_id", "mission_name",
    "timestamp", "latitude", "longitude",
    "radiation_value", "dose_rate_usvh",
    "pm25", "pm10",
    "roll", "pitch", "yaw", "pressure_baro", "altitude_baro",
]


# ──────────────────────────────────────────────────────────────────────
# 1 + 2. Geometry round-trip and coordinate order
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.geo
class TestGeometryRoundTrip:

    def test_properties_derive_from_location(self, sensor_log_at):
        log = sensor_log_at(-1.2921, 36.8219)
        assert log.latitude == pytest.approx(-1.2921)
        assert log.longitude == pytest.approx(36.8219)
        assert log.location.y == pytest.approx(-1.2921)
        assert log.location.x == pytest.approx(36.8219)

    def test_survives_a_database_round_trip(self, sensor_log_at):
        """Values must come back off disk unchanged, not just off the instance."""
        created = sensor_log_at(-1.2954404, 36.8241743)
        fetched = SensorLog.objects.get(pk=created.pk)
        assert fetched.latitude == pytest.approx(-1.2954404, abs=1e-9)
        assert fetched.longitude == pytest.approx(36.8241743, abs=1e-9)

    def test_srid_is_4326(self, sensor_log_at):
        log = sensor_log_at(-1.29, 36.82)
        assert log.location.srid == 4326

    def test_geometry_is_2d(self, sensor_log_at):
        """ADR-0011: 2D only. Altitude lives on ImuBaroLog, not in the point."""
        log = sensor_log_at(-1.29, 36.82)
        assert not log.location.hasz


@pytest.mark.geo
class TestCoordinateOrderGuard:
    """point_from_latlon is the ONLY sanctioned way to build a position."""

    def test_flips_lat_lon_into_point_x_y(self):
        point = point_from_latlon(lat=-1.2921, lon=36.8219)
        assert point.x == pytest.approx(36.8219), "x must be LONGITUDE"
        assert point.y == pytest.approx(-1.2921), "y must be LATITUDE"

    def test_rejects_transposed_arguments(self):
        """The inversion tripwire. Both values are individually valid — only
        the region check distinguishes them."""
        with pytest.raises(ValueError, match="outside the expected region"):
            point_from_latlon(lat=36.8219, lon=-1.2921)

    def test_arguments_are_keyword_only(self):
        with pytest.raises(TypeError):
            point_from_latlon(-1.2921, 36.8219)  # positional: unrepresentable

    def test_rejects_out_of_range_values(self):
        with pytest.raises(ValueError, match="Latitude out of range"):
            point_from_latlon(lat=91.0, lon=36.8, region=None)
        with pytest.raises(ValueError, match="Longitude out of range"):
            point_from_latlon(lat=-1.29, lon=181.0, region=None)

    def test_region_none_allows_coordinates_outside_kenya(self):
        """Satellite AOIs and imported datasets are legitimately elsewhere."""
        point = point_from_latlon(lat=48.8566, lon=2.3522, region=None)
        assert point.x == pytest.approx(2.3522)

    def test_kenya_bbox_contains_the_simulator_origin(self):
        min_lon, min_lat, max_lon, max_lat = KENYA_BBOX
        assert min_lat <= -1.2921 <= max_lat
        assert min_lon <= 36.8219 <= max_lon


# ──────────────────────────────────────────────────────────────────────
# 3 + 4. API contract: GeoJSON order, CSV header, null safety
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApiContract:

    def test_map_data_emits_lng_lat_order(self, authed_client, sensor_log_at, robot):
        """GeoJSON is [lng, lat]. Same order as PostGIS (x, y) — no flip.

        Asserting on the VALUES, not just the field names: a swap here would
        still produce a syntactically valid FeatureCollection.
        """
        sensor_log_at(-1.2921, 36.8219, robot=robot)
        response = authed_client.get(reverse("map-data"))
        assert response.status_code == 200

        coords = response.data["features"][0]["geometry"]["coordinates"]
        assert coords[0] == pytest.approx(36.8219), "position 0 must be LONGITUDE"
        assert coords[1] == pytest.approx(-1.2921), "position 1 must be LATITUDE"

    def test_csv_header_is_stable(self, authed_client, sensor_log_at, robot):
        sensor_log_at(-1.29, 36.82, robot=robot, radiation=42.0)
        response = authed_client.get(reverse("data-log-export-csv"))
        assert response.status_code == 200

        body = response.content.decode()
        header = next(csv.reader(io.StringIO(body)))
        assert header == EXPECTED_CSV_HEADER

    def test_serializer_exposes_latitude_longitude(self, sensor_log_at, robot):
        """The property shim must be invisible to the serializer's output."""
        log = sensor_log_at(-1.2921, 36.8219, robot=robot)
        data = DataLogSerializer(log).data
        assert data["latitude"] == pytest.approx(-1.2921)
        assert data["longitude"] == pytest.approx(36.8219)

    def test_serializes_log_with_no_reading_rows(self, sensor_log_at, robot):
        """F05 regression: a robot without imu_baro (or any sensor) still
        serializes — reading access is null-safe, not assumed present."""
        log = sensor_log_at(-1.29, 36.82, robot=robot)
        data = DataLogSerializer(log).data
        assert data["radiation_value"] is None
        assert data["pm25"] is None
        assert data["altitude_baro"] is None
        assert data["latitude"] is not None  # position always present

    def test_serializes_log_with_partial_readings(self, sensor_log_at, robot):
        log = sensor_log_at(-1.29, 36.82, robot=robot, radiation=55.0)
        data = DataLogSerializer(log).data
        assert data["radiation_value"] == pytest.approx(55.0)
        assert data["pm25"] is None


# ──────────────────────────────────────────────────────────────────────
# 5. Spatial queries — the point of the whole feature
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.geo
@pytest.mark.django_db
class TestSpatialQueries:

    def test_within_bbox_returns_matching_rows(self, sensor_log_at):
        sensor_log_at(-1.2921, 36.8219)   # inside
        sensor_log_at(-1.2930, 36.8228)   # inside
        sensor_log_at(3.5000, 40.5000)    # Marsabit — far outside

        box = polygon_from_bbox(36.80, -1.30, 36.83, -1.28)
        assert SensorLog.objects.filter(location__within=box).count() == 2

    def test_distant_bbox_returns_nothing(self, sensor_log_at):
        """The check a systematic inversion would fail: inverted Nairobi points
        land near (36.8 lat, -1.3 lon), which is not in ANY Kenyan bbox."""
        sensor_log_at(-1.2921, 36.8219)
        far = polygon_from_bbox(40.0, 3.0, 41.0, 4.0)
        assert SensorLog.objects.filter(location__within=far).count() == 0

    def test_polygon_containment_via_mission_aoi(self, sensor_log_at, mission):
        """F10.2/F10.4 shape: scope logs to a mission's area of interest."""
        mission.area_of_interest = polygon_from_bbox(36.80, -1.30, 36.83, -1.28)
        mission.save(update_fields=["area_of_interest"])

        inside = sensor_log_at(-1.2921, 36.8219, mission=mission)
        sensor_log_at(3.5, 40.5, mission=mission)  # outside the AOI

        matched = SensorLog.objects.filter(location__within=mission.area_of_interest)
        assert list(matched.values_list("id", flat=True)) == [inside.id]

    def test_distance_ordering_works(self, sensor_log_at):
        """Nearest-point lookup — the primitive F10.4 correlation is built on."""
        from django.contrib.gis.db.models.functions import Distance

        near = sensor_log_at(-1.2921, 36.8219)
        sensor_log_at(-1.4000, 36.9000)

        origin = point_from_latlon(lat=-1.2921, lon=36.8219)
        closest = SensorLog.objects.annotate(
            d=Distance("location", origin)
        ).order_by("d").first()
        assert closest.id == near.id


# ──────────────────────────────────────────────────────────────────────
# 6. Tenancy (ADR-0006) survives the schema change
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOrgScoping:

    def test_map_data_excludes_other_orgs(
        self, authed_client, sensor_log_at, robot, other_robot
    ):
        sensor_log_at(-1.2921, 36.8219, robot=robot)
        sensor_log_at(-1.2930, 36.8228, robot=other_robot)

        response = authed_client.get(reverse("map-data"))
        assert len(response.data["features"]) == 1

    def test_data_logs_excludes_other_orgs(
        self, authed_client, sensor_log_at, robot, other_robot
    ):
        sensor_log_at(-1.2921, 36.8219, robot=robot)
        sensor_log_at(-1.2930, 36.8228, robot=other_robot)

        response = authed_client.get(reverse("data-log-list"))
        assert response.data["count"] == 1
# ─── RANGER V3 END: core geo + contract tests ───