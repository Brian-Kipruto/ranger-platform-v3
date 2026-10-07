# ─── RANGER V3 START: 11-ingest-region ───
"""Region registry (F11). Pure Python — no DB, no ROS.

The Kenya default must not move; Rabat must accept Rabat and nothing else;
a lat/lon swap must still be caught under every named region.
"""
import inspect

import pytest

from core.geo import (
    KENYA_BBOX,
    RABAT_BBOX,
    RABAT_VENUE,
    REGION_CHOICES,
    REGIONS,
    point_from_latlon,
    resolve_region,
)

NAIROBI = (-1.2921, 36.8219)
RABAT = RABAT_VENUE                      # (34.02, -6.84) until the venue is confirmed
RABAT_SWAPPED = (RABAT[1], RABAT[0])     # (-6.84, 34.02) — lands in Tanzania

# Minimum distance (degrees) from the venue to every edge of the Rabat box.
VENUE_MARGIN_DEG = 0.3


def _inside(bbox, lat, lon):
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


@pytest.mark.geo
class TestKenyaDefaultUnchanged:

    def test_default_region_is_still_kenya(self):
        default = inspect.signature(point_from_latlon).parameters["region"].default
        assert default is KENYA_BBOX
        assert KENYA_BBOX == (33.9, -4.7, 41.9, 5.5)

    def test_kenya_name_resolves_to_the_same_box(self):
        assert resolve_region("kenya") is KENYA_BBOX

    def test_rabat_rejected_under_the_default(self):
        """Today's bug, kept as a guarantee: no region given = Kenya only."""
        with pytest.raises(ValueError, match="outside the expected region"):
            point_from_latlon(lat=RABAT[0], lon=RABAT[1])


@pytest.mark.geo
class TestRabat:

    def test_accepts_the_venue_with_northwest_signs(self):
        p = point_from_latlon(lat=RABAT[0], lon=RABAT[1], region=resolve_region("rabat"))
        assert p.y > 0, "Rabat latitude must be NORTH (positive)"
        assert p.x < 0, "Rabat longitude must be WEST (negative)"

    def test_rejects_nairobi(self):
        with pytest.raises(ValueError, match="outside the expected region"):
            point_from_latlon(lat=NAIROBI[0], lon=NAIROBI[1], region=resolve_region("rabat"))

    def test_rejects_swapped_rabat(self):
        """The inversion tripwire. (-6.84, 34.02) is a valid point in Tanzania."""
        with pytest.raises(ValueError, match="outside the expected region"):
            point_from_latlon(lat=RABAT_SWAPPED[0], lon=RABAT_SWAPPED[1],
                              region=resolve_region("rabat"))

    def test_swapped_rabat_also_rejected_under_kenya(self):
        with pytest.raises(ValueError, match="outside the expected region"):
            point_from_latlon(lat=RABAT_SWAPPED[0], lon=RABAT_SWAPPED[1])

    def test_venue_sits_inside_box_with_margin(self):
        """Catches a bbox typed in lat-first order, and a venue update that
        forgot to move the box."""
        lat, lon = RABAT_VENUE
        min_lon, min_lat, max_lon, max_lat = RABAT_BBOX
        assert min(lat - min_lat, max_lat - lat,
                   lon - min_lon, max_lon - lon) >= VENUE_MARGIN_DEG


@pytest.mark.geo
class TestRegistry:

    def test_none_skips_the_box(self):
        assert resolve_region("none") is None
        p = point_from_latlon(lat=RABAT_SWAPPED[0], lon=RABAT_SWAPPED[1],
                              region=resolve_region("none"))
        assert p.x == pytest.approx(RABAT_SWAPPED[1])

    @pytest.mark.parametrize("bad", ["", "Rabat", "KENYA", "morocco", None, "kenya "])
    def test_unknown_name_raises(self, bad):
        with pytest.raises(ValueError, match="Unknown region"):
            resolve_region(bad)

    def test_choices_are_exactly_the_registry_plus_none(self):
        assert REGION_CHOICES == ("kenya", "rabat", "none")

    @pytest.mark.parametrize("name", sorted(REGIONS))
    def test_every_box_is_well_formed(self, name):
        min_lon, min_lat, max_lon, max_lat = REGIONS[name]
        assert -180 <= min_lon < max_lon <= 180
        assert -90 <= min_lat < max_lat <= 90

    def test_regions_do_not_overlap(self):
        """A point valid in two regions would make the region choice meaningless."""
        k, r = KENYA_BBOX, RABAT_BBOX
        disjoint = k[2] < r[0] or r[2] < k[0] or k[3] < r[1] or r[3] < k[1]
        assert disjoint
# ─── RANGER V3 END: 11-ingest-region ───
