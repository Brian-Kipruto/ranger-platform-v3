# ─── RANGER V3 START: 11-ingest-region ───
"""
F11: the N/W sign path, proven on the PC before Morocco.

nmea_sim (robot/tools) writes GGA; gps_node parses it with pynmea2 and
publishes msg.latitude / msg.longitude as-is. Every fix this stack has ever
seen was S/E. Here all four quadrants go sim -> pynmea2 -> signed degrees,
and the Rabat site goes on through the real region guard.
"""
import importlib.util
from pathlib import Path

import pynmea2
import pytest

from core.geo import RABAT_VENUE, point_from_latlon, resolve_region

_SIM = Path(__file__).resolve().parents[2] / "robot" / "tools" / "nmea_sim.py"
_spec = importlib.util.spec_from_file_location("nmea_sim", _SIM)
nmea_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nmea_sim)


def _parse(line):
    """Exactly gps_node.handle_gga's parse, with the checksum enforced."""
    msg = pynmea2.parse(line.strip(), check=True)
    return msg.latitude, msg.longitude


QUADRANTS = {
    "NE paris":   (48.8566, 2.3522),
    "NW rabat":   (34.02, -6.84),
    "SE nairobi": (-1.2864, 36.8172),
    "SW rio":     (-22.9068, -43.1729),
}


@pytest.mark.parametrize("name", QUADRANTS)
def test_every_quadrant_round_trips_with_correct_signs(name):
    lat, lon = QUADRANTS[name]
    got_lat, got_lon = _parse(nmea_sim.gga(True, site=(lat, lon, 100.0), jitter_min=0))
    assert got_lat == pytest.approx(lat, abs=1e-6)
    assert got_lon == pytest.approx(lon, abs=1e-6)


def test_rabat_site_is_north_west():
    for _ in range(50):  # with the default jitter
        lat, lon = _parse(nmea_sim.gga(True, site=nmea_sim.SITES["rabat"]))
        assert lat > 0 and lon < 0
        assert lat == pytest.approx(RABAT_VENUE[0], abs=1e-3)
        assert lon == pytest.approx(RABAT_VENUE[1], abs=1e-3)


def test_nairobi_default_is_south_east():
    for _ in range(50):
        lat, lon = _parse(nmea_sim.gga(True))
        assert lat < 0 and lon > 0
        assert lat == pytest.approx(-1.2864, abs=1e-3)
        assert lon == pytest.approx(36.8172, abs=1e-3)


def test_sim_rabat_site_matches_the_region_venue():
    """Two copies (robot code can't import Django). Keep them equal."""
    assert nmea_sim.SITES["rabat"][:2] == RABAT_VENUE


@pytest.mark.geo
def test_parsed_rabat_fix_passes_rabat_guard_and_fails_kenya():
    lat, lon = _parse(nmea_sim.gga(True, site=nmea_sim.SITES["rabat"]))
    point_from_latlon(lat=lat, lon=lon, region=resolve_region("rabat"))
    with pytest.raises(ValueError, match="outside the expected region"):
        point_from_latlon(lat=lat, lon=lon)


def test_no_fix_sentence_has_no_coordinates():
    msg = pynmea2.parse(nmea_sim.gga(False).strip(), check=True)
    assert int(msg.gps_qual) == 0
    assert msg.lat == "" and msg.lon == ""
# ─── RANGER V3 END: 11-ingest-region ───
