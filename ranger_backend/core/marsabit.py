# ─── RANGER V3 START: marsabit survey reference data ───
"""
Reference data for the KNRA Marsabit County radiological survey.

Source
------
Kenya Nuclear Regulatory Authority, "Radiological and Geochemical Assessment
of Former Oil Exploration Sites in Marsabit County, Kenya", April 2026.
Fieldwork 1-5 July 2024, under the National Environmental Radioactivity
Mapping Programme.

What this module is, and is not
-------------------------------
The raw per-point survey logs are NOT available to this project. Only the
published report is. Everything here is therefore one of two things:

  * PUBLISHED  — values printed in the report (site bounds, n, mean, SD, min,
                 max, skew). Real numbers, citable.
  * DERIVED    — point clouds generated to match those statistics. The SHAPE
                 is faithful; the individual points are fiction.

Any SensorLog created from the derived clouds is labelled
`SensorLog.Source.MODELLED`. Never `reported`, and never `live`. A modelled
reading presented as a measurement is the one failure this whole provenance
system exists to prevent.

Site bounds are read from the report's figure axes (Figs 3.1-3.7) and are
accurate to roughly the plotted precision. They are good enough to scope a
satellite AOI; they are NOT a substitute for the survey's own GPS records.
"""
from datetime import date

# Survey window, from the report's methodology section.
SURVEY_START = date(2024, 7, 1)
SURVEY_END = date(2024, 7, 5)

CITATION = "KNRA Marsabit survey, April 2026 (fieldwork Jul 2024)"

# Instrument logging intervals, report §2.2.1. Used to space timestamps so a
# generated transect has the cadence a real one would.
PGIS_INTERVAL_S = 1
BGEIGIE_INTERVAL_S = 5

# bGeigie Nano / LND-7317 pancake tube: CPM -> uSv/h uses ~334 CPM per uSv/h.
# The report publishes dose rates, not counts, so counts here are BACK-
# CALCULATED through this factor. Treat radiation_value on modelled rows as
# derived, not measured — the dose rate is the primary quantity.
CPM_PER_USVH = 334.0

# ── Sites ────────────────────────────────────────────────────────────────
# bbox: (min_lon, min_lat, max_lon, max_lat) — the polygon_from_bbox order.
# Dose-rate statistics: report Table 3.1, in nSv/h.
SITES = [
    {
        "code": "kargi",
        "name": "Kargi (Sirius) Oil Well Site",
        "area": "Kargi",
        "bbox": (37.5472, 2.5798, 37.5482, 2.5808),
        "n": 2347, "mean": 55.0, "sd": 31.0, "min": 26.0, "max": 180.0, "skew": 2.0,
        "description": (
            "Former Amoco exploration well. Soil Pb 436 ppm and Zn 314 ppm "
            "exceed WHO agricultural limits (report Table 3.6)."
        ),
    },
    {
        "code": "boji",
        "name": "Boji",
        "area": "Maikona",
        "bbox": (37.6410, 2.8858, 37.6450, 2.8885),
        "n": 2023, "mean": 46.0, "sd": 30.0, "min": 18.0, "max": 168.0, "skew": 2.0,
        "description": (
            "Suspected historical dumping area. Highest geochemical anomalies "
            "in the survey: soil Pb 616 ppm, Cu 454 ppm, Zn 794 ppm; water "
            "Fe 32 mg/L and As 0.016 mg/L, both above WHO limits."
        ),
    },
    {
        "code": "gamura",
        "name": "Gamura",
        "area": "Maikona",
        "bbox": (37.5796, 2.9345, 37.5810, 2.9365),
        "n": 2237, "mean": 79.0, "sd": 37.0, "min": 34.0, "max": 290.0, "skew": 2.0,
        "description": (
            "Temporary settlement and former prospector camp with borehole. "
            "Water As 0.009 mg/L; soil Cu and Zn elevated."
        ),
    },
    {
        "code": "dukana-w1",
        "name": "Dukana (Laga Balal) Well 1",
        "area": "Dukana",
        "bbox": (37.2464, 3.5604, 37.2472, 3.5614),
        "n": 1279, "mean": 73.0, "sd": 36.0, "min": 48.0, "max": 272.0, "skew": 3.0,
        "description": (
            "Amoco Laga Balal #1, drilled 22 December 1985. Landsat 5 has NO "
            "coverage of this site between 1985-04-15 and 1986-01-12, so the "
            "drilling was never imaged; the archive is a landscape baseline "
            "here, not a change-detection subject (verified 2026-08-05)."
        ),
    },
    {
        "code": "dukana-w2",
        "name": "Dukana (Laga Balal) Well 2",
        "area": "Dukana",
        "bbox": (37.2443, 3.5548, 37.2448, 3.5556),
        "n": 687, "mean": 82.0, "sd": 36.0, "min": 51.0, "max": 228.0, "skew": 2.0,
        "description": "Second well at the Laga Balal site.",
    },
    {
        "code": "balesa",
        "name": "Balesa Shopping Centre (Kalacha)",
        "area": "Kalacha",
        "bbox": (37.3465, 3.6105, 37.3480, 3.6120),
        "n": 1689, "mean": 87.0, "sd": 50.0, "min": 37.0, "max": 266.0, "skew": 1.0,
        "description": (
            "CONTROL SITE. Public shopping centre, no association with "
            "prospecting or dumping. Any correlation method must reproduce "
            "background here, or it is detecting something other than site "
            "disturbance."
        ),
    },
    {
        "code": "forole",
        "name": "Forole Hills foothills",
        "area": "Forole",
        "bbox": (37.9668, 3.7160, 37.9678, 3.7175),
        "n": 1819, "mean": 140.0, "sd": 78.0, "min": 72.0, "max": 1000.0, "skew": 10.0,
        "description": (
            "Dwellings in the foothills near the Kenya-Ethiopia border. The "
            "survey's only localized anomalies (>300 nSv/h, isolated readings "
            "past 1 uSv/h), skew 10 and kurtosis 105. Soil Zr 2185 ppm "
            "suggests heavy-mineral or volcanic-derived sediment. The report "
            "recommends targeted follow-up here — this is the site a return "
            "visit with a rover would target."
        ),
    },
]

SITES_BY_CODE = {s["code"]: s for s in SITES}


def site_bbox(code):
    return SITES_BY_CODE[code]["bbox"]
# ─── RANGER V3 END: marsabit survey reference data ───
