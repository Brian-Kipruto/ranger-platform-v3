# ─── RANGER V3 START: geospatial helpers ───
"""
The single place where latitude/longitude become a PostGIS geometry.

Why this module exists
----------------------
PostGIS `Point(x, y)` takes **(longitude, latitude)** — the reverse of how
humans say "lat/lon". Getting it backwards does not raise: a Kenyan reading
at (-1.29, 36.82) inverted becomes (36.82, -1.29), which is a perfectly valid
coordinate somewhere in the Indian Ocean off Somalia. It renders on a map. It
passes every type check. You find out weeks later when a correlation returns
nothing.

Every write path — the simulator, the ROS bridge (F08/F09), satellite
ingestion (F10.2) — funnels through `point_from_latlon` so that mistake can
only be made in one place, and that place asserts against it.

The arguments are keyword-only on purpose. `point_from_latlon(lat, lon)`
positionally would be exactly as invertible as the thing we're guarding
against.

See ADR-0011 for the geometry/SRID decision (geometry(Point,4326), 2D).
"""
from django.contrib.gis.geos import Point, Polygon

# WGS84. Matches GeoJSON and MapLibre directly, so no transform on read.
SRID_WGS84 = 4326

# Kenya's national bounding box, generously rounded: (min_lon, min_lat, max_lon, max_lat).
# Used as an inversion tripwire, not as a business rule — see `region` below.
KENYA_BBOX = (33.9, -4.7, 41.9, 5.5)


def point_from_latlon(*, lat: float, lon: float, region=KENYA_BBOX) -> Point:
    """Build a WGS84 Point from a latitude/longitude pair.

    Args:
        lat: Latitude, degrees north (negative south). Kenya is ~-4.7 to 5.5.
        lon: Longitude, degrees east. Kenya is ~33.9 to 41.9.
        region: (min_lon, min_lat, max_lon, max_lat) sanity box, or None to
            skip. Defaults to Kenya. Pass `region=None` for legitimately
            out-of-region data (a satellite AOI elsewhere, imported datasets).

    Returns:
        Point(lon, lat, srid=4326) — note the argument ORDER FLIP, which is
        the entire reason this function exists.

    Raises:
        ValueError: if the coordinates are non-numeric, outside global valid
            ranges, or outside `region`.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Non-numeric coordinate: lat={lat!r} lon={lon!r}") from exc

    # Global range check. Note this does NOT catch inversion for Kenyan data:
    # 36.82 is a valid latitude and -1.29 is a valid longitude. Only the
    # region check below catches that case.
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude out of range: {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Longitude out of range: {lon}")

    if region is not None:
        min_lon, min_lat, max_lon, max_lat = region
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            raise ValueError(
                f"Coordinate (lat={lat}, lon={lon}) falls outside the expected "
                f"region {region}. If the arguments are swapped this is exactly "
                f"what you would see. If the location is genuinely outside the "
                f"region, pass region=None."
            )

    # THE FLIP: Point takes (x, y) == (longitude, latitude).
    return Point(lon, lat, srid=SRID_WGS84)


def polygon_from_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Polygon:
    """Build a WGS84 Polygon from a bounding box.

    Used by spatial-query verification now, and by satellite AOI / scene
    footprint work in F10.2-F10.4.
    """
    poly = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))
    poly.srid = SRID_WGS84
    return poly
# ─── RANGER V3 END: geospatial helpers ───
