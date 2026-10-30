# ─── RANGER V3 START: 16-report-thresholds ───
"""Reference levels and comparisons (F16 fork 3)."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from reports import stats, thresholds as th

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def point(i, *, dose=None, rad_src=None, pm25=None, pm10=None, aq_src=None):
    return {"timestamp": T0 + timedelta(seconds=i), "lat": -1.29 + i * 1e-5,
            "lon": 36.82, "source": "live",
            "dose_rate_usvh": dose, "cpm": None, "radiation_source": rad_src,
            "pm25": pm25, "pm10": pm10, "air_quality_source": aq_src}


def run(points):
    rows = [{
        "timestamp": p["timestamp"], "source": p["source"], "provenance_note": "",
        "radiation_data__source": p["radiation_source"],
        "air_quality_data__source": p["air_quality_source"],
        "imu_baro_data__source": None,
        "radiation_data__dose_rate_usvh": p["dose_rate_usvh"],
        "radiation_data__radiation_value": p["cpm"],
        "air_quality_data__pm25": p["pm25"], "air_quality_data__pm10": p["pm10"],
    } for p in points]
    summary = stats.summarise(rows)
    return th.compare(summary, points)


def rows_for(c, quantity, source):
    return [r for r in c["rows"] if r["quantity"] == quantity and r["source"] == source]


class TestRegistry:
    def test_every_entry_cited_and_labelled(self):
        for r in th.REFERENCES:
            assert r.citation.strip(), r.key
            assert r.kind in {"investigation level", "guideline", "background"}, r.key
            assert r.use in {th.EXCEEDANCE, th.MEAN_ONLY, th.CONTEXT}, r.key
            assert "limit" not in r.kind.lower(), r.key

    def test_values_as_verified(self):
        by = {r.key: r for r in th.REFERENCES}
        assert by["knra-marsabit-investigation"].value == 0.300
        assert by["unscear-2000-outdoor-terrestrial"].value == 59.0
        assert by["unscear-2000-outdoor-terrestrial"].unit == "nGy/h"
        assert by["who-2021-pm25-24h"].value == 15.0
        assert by["who-2021-pm10-24h"].value == 45.0

    def test_pm_is_never_per_reading(self):
        for r in th.REFERENCES:
            if r.quantity in ("pm25", "pm10"):
                assert r.use == th.MEAN_ONLY

    def test_unscear_is_context_only(self):
        assert th.references_for("dose_rate_usvh")[1].use == th.CONTEXT


class TestExceedance:
    def test_strictly_above(self):
        c = run([point(0, dose=0.3, rad_src="live"), point(1, dose=0.31, rad_src="live"),
                 point(2, dose=0.1, rad_src="live")])
        r, = rows_for(c, "dose_rate_usvh", "live")
        assert (r["n_above"], r["n"]) == (1, 3)
        assert r["pct_above"] == pytest.approx(100 / 3)

    def test_per_tier_never_pooled(self):
        c = run([point(0, dose=0.5, rad_src="live"), point(1, dose=0.5, rad_src="simulated"),
                 point(2, dose=0.1, rad_src="simulated")])
        assert rows_for(c, "dose_rate_usvh", "live")[0]["n_above"] == 1
        assert rows_for(c, "dose_rate_usvh", "simulated")[0]["n_above"] == 1
        assert rows_for(c, "dose_rate_usvh", "simulated")[0]["n"] == 2

    def test_list_sorted_and_capped(self):
        pts = [point(i, dose=0.31 + i * 0.01, rad_src="live") for i in range(40)]
        c = run(pts)
        lst, = c["exceedance_lists"]
        assert lst["total"] == 40 and len(lst["rows"]) == th.LIST_CAP
        values = [x["value"] for x in lst["rows"]]
        assert values == sorted(values, reverse=True) and values[0] == pytest.approx(0.70)

    def test_modelled_gets_count_not_list(self):
        c = run([point(i, dose=0.5, rad_src="modelled") for i in range(3)])
        r, = rows_for(c, "dose_rate_usvh", "modelled")
        assert r["n_above"] == 3 and "MODELLED" in r["list_withheld"]
        assert c["exceedance_lists"] == []

    def test_nothing_above_no_list(self):
        c = run([point(0, dose=0.1, rad_src="live")])
        assert c["exceedance_lists"] == [] and "list_withheld" not in c["rows"][0]


class TestMeanOnly:
    def test_pm_mean_above_and_below(self):
        c = run([point(0, pm25=20.0, pm10=10.0, aq_src="simulated"),
                 point(600, pm25=20.0, pm10=10.0, aq_src="simulated")])
        pm25, = rows_for(c, "pm25", "simulated")
        pm10, = rows_for(c, "pm10", "simulated")
        assert pm25["mean_above"] is True and pm10["mean_above"] is False
        assert pm25["window_seconds"] == 600
        assert "n_above" not in pm25

    def test_mean_printed_to_resolve_against_level(self):
        # Mission 12: PM2.5 mean 14.9613 vs 15 printed "15.0 ... below 15.0".
        assert th.resolving_decimals(14.9613, 15.0, 1) == 2   # 14.96
        assert th.resolving_decimals(26.1161, 45.0, 1) == 1   # 26.1, already clear
        assert th.resolving_decimals(15.0, 15.0, 1) == 1      # equal stays equal
        assert th.resolving_decimals(15.00001, 15.0, 1) == 4  # capped
        c = run([point(0, pm25=14.9613, pm10=10.0, aq_src="simulated")])
        assert rows_for(c, "pm25", "simulated")[0]["mean_decimals"] == 2

    def test_no_pm_list_ever(self):
        c = run([point(i, pm25=99.0, pm10=99.0, aq_src="live") for i in range(5)])
        assert c["exceedance_lists"] == []


class TestScope:
    def test_cpm_never_compared(self):
        pts = [point(0, rad_src="simulated")]
        pts[0]["cpm"] = 500.0
        c = run(pts)
        assert c["rows"] == []
        assert any("CPM" in n for n in c["not_compared"])

    def test_context_and_citations_only_when_relevant(self):
        c = run([point(0, pm25=10.0, pm10=10.0, aq_src="live")])
        assert c["context"] == []                     # no dose -> no UNSCEAR
        assert all("WHO" in x for x in c["citations"])
        c = run([point(0, dose=0.1, rad_src="live")])
        assert [x["key"] for x in c["context"]] == ["unscear-2000-outdoor-terrestrial"]
        assert any("UNSCEAR" in x for x in c["citations"])
        assert not any("WHO" in x for x in c["citations"])


@pytest.mark.django_db
class TestInPdf:
    def test_no_pass_fail_language_and_levels_printed(self, mission, sensor_log_at, settings, tmp_path):
        from pypdf import PdfReader
        from missions.models import Mission
        from reports.generate import generate_report
        settings.MEDIA_ROOT = tmp_path
        for i, cpm in enumerate((40.0, 60.0, 80.0)):  # dose = cpm * 0.0057 -> 0.228..0.456
            sensor_log_at(-1.29 - i * 1e-4, 36.82, mission=mission, radiation=cpm,
                          pm25=20.0, pm10=30.0)
        mission.status = Mission.Status.COMPLETED
        mission.save(update_fields=["status"])
        r = generate_report(mission)
        text = " ".join(" ".join(p.extract_text() for p in PdfReader(tmp_path / r.pdf_path).pages).split())
        assert not re.search(r"\b(PASS|FAIL|PASSED|FAILED|COMPLIANT)\b", text, re.I)
        assert "investigation level" in text and "guideline" in text
        assert "2 of 3 readings above" in text
        assert "Registry 2026-10-30" in text
        assert r.summary["comparisons"]["registry_version"] == th.REGISTRY_VERSION
    def test_borderline_mean_printed_unambiguously(self, mission, sensor_log_at, settings, tmp_path):
        from pypdf import PdfReader
        from missions.models import Mission
        from reports.generate import generate_report
        settings.MEDIA_ROOT = tmp_path
        sensor_log_at(-1.29, 36.82, mission=mission, radiation=10.0, pm25=14.9613, pm10=10.0)
        mission.status = Mission.Status.COMPLETED
        mission.save(update_fields=["status"])
        r = generate_report(mission)
        text = " ".join(" ".join(p.extract_text() for p in PdfReader(tmp_path / r.pdf_path).pages).split())
        assert "Survey mean 14.96 µg/m³, below the guideline value" in text
# ─── RANGER V3 END: 16-report-thresholds ───
