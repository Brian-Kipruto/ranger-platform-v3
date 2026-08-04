# ─── RANGER V3 START: missions geo tests ───
"""
Waypoint geometry and Mission.area_of_interest (F10.1).

Waypoints get their own coverage because they are INVISIBLE to the API
contract diff — no endpoint serializes them, so capture.sh/compare.sh cannot
see a regression here. An inverted waypoint doesn't raise; it makes the
simulator drive toward a target in the wrong place, and you find out much
later. These tests are the only guard on that path.
"""
import pytest

from core.geo import point_from_latlon, polygon_from_bbox
from missions.models import Mission, Waypoint


@pytest.mark.geo
@pytest.mark.django_db
class TestWaypointGeometry:

    def test_properties_derive_from_location(self, waypoint_at):
        wp = waypoint_at(-1.2921, 36.8219)
        assert wp.latitude == pytest.approx(-1.2921)
        assert wp.longitude == pytest.approx(36.8219)

    def test_survives_database_round_trip(self, waypoint_at):
        created = waypoint_at(-1.2950, 36.8240)
        fetched = Waypoint.objects.get(pk=created.pk)
        assert fetched.latitude == pytest.approx(-1.2950, abs=1e-9)
        assert fetched.longitude == pytest.approx(36.8240, abs=1e-9)

    def test_ordered_route_keeps_coordinates_aligned(self, waypoint_at):
        """The simulator reads waypoints in `order` and steers by the deltas.
        A single inverted point would send it across the country."""
        route = [(-1.2921, 36.8219), (-1.2930, 36.8228), (-1.2940, 36.8235)]
        for idx, (lat, lon) in enumerate(route):
            waypoint_at(lat, lon, order=idx)

        stored = Waypoint.objects.order_by("order")
        for (lat, lon), wp in zip(route, stored):
            assert wp.location.y == pytest.approx(lat), f"wp#{wp.order} latitude"
            assert wp.location.x == pytest.approx(lon), f"wp#{wp.order} longitude"

    def test_location_is_required(self, mission):
        """Waypoint.location is NOT NULL after missions.0004."""
        from django.db.utils import IntegrityError

        with pytest.raises((IntegrityError, ValueError)):
            Waypoint.objects.create(mission=mission, order=0)


@pytest.mark.geo
@pytest.mark.django_db
class TestMissionAreaOfInterest:

    def test_defaults_to_null(self, mission):
        """Most missions have no defined boundary — that's a normal state,
        not missing data, so the column stays permanently nullable."""
        assert mission.area_of_interest is None

    def test_accepts_a_polygon(self, mission):
        mission.area_of_interest = polygon_from_bbox(36.80, -1.30, 36.83, -1.28)
        mission.save(update_fields=["area_of_interest"])

        fetched = Mission.objects.get(pk=mission.pk)
        assert fetched.area_of_interest is not None
        assert fetched.area_of_interest.srid == 4326

    def test_contains_expected_points(self, mission):
        """The F10.2 shape: does this AOI cover a given ground position?"""
        mission.area_of_interest = polygon_from_bbox(36.80, -1.30, 36.83, -1.28)
        mission.save(update_fields=["area_of_interest"])

        inside = point_from_latlon(lat=-1.2921, lon=36.8219)
        outside = point_from_latlon(lat=3.5, lon=40.5)
        assert mission.area_of_interest.contains(inside)
        assert not mission.area_of_interest.contains(outside)

    def test_waypoints_fall_within_their_mission_aoi(self, mission, waypoint_at):
        mission.area_of_interest = polygon_from_bbox(36.80, -1.30, 36.83, -1.28)
        mission.save(update_fields=["area_of_interest"])

        wp = waypoint_at(-1.2921, 36.8219)
        matched = Waypoint.objects.filter(location__within=mission.area_of_interest)
        assert list(matched.values_list("id", flat=True)) == [wp.id]
# ─── RANGER V3 END: missions geo tests ───