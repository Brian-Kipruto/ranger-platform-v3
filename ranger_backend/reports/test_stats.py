# ─── RANGER V3 START: 16-report-stats ───
"""Report arithmetic (F16 fork 7). Pure: no database."""
from datetime import datetime, timedelta, timezone

import pytest

from reports import stats

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(i=0, *, pos="live", note="", rad=None, rad_src=None, cpm=None,
        aq_src=None, pm25=None, pm10=None, imu_src=None):
    return {
        "timestamp": T0 + timedelta(seconds=i),
        "source": pos,
        "provenance_note": note,
        "radiation_data__source": rad_src,
        "air_quality_data__source": aq_src,
        "imu_baro_data__source": imu_src,
        "radiation_data__dose_rate_usvh": rad,
        "radiation_data__radiation_value": cpm,
        "air_quality_data__pm25": pm25,
        "air_quality_data__pm10": pm10,
    }


def block(summary, quantity, source):
    hits = [b for b in summary["quantities"]
            if b["quantity"] == quantity and b["source"] == source]
    assert len(hits) <= 1
    return hits[0] if hits else None


class TestWeakest:
    def test_tier_order_is_most_to_least_authoritative(self):
        assert stats.TIERS == ["live", "reported", "modelled", "simulated"]

    def test_weakest_is_least_authoritative_not_majority(self):
        # 999 live positions, ONE simulated radiation reading -> simulated.
        rows = [row(i) for i in range(999)]
        rows.append(row(999, rad=0.1, rad_src="simulated", cpm=10))
        assert stats.summarise(rows)["weakest_source"] == "simulated"

    def test_reading_source_counts_not_row_source(self):
        # Live position, modelled radiation: the report is modelled (ADR-0020).
        s = stats.summarise([row(0, pos="live", rad=0.1, rad_src="modelled", cpm=33)])
        assert s["weakest_source"] == "modelled"
        assert s["provenance_matrix"]["position"]["live"] == 1
        assert s["provenance_matrix"]["radiation"]["modelled"] == 1

    def test_all_live(self):
        s = stats.summarise([row(0, rad=0.1, rad_src="live", cpm=17)])
        assert s["weakest_source"] == "live"

    def test_absent_kinds_not_in_matrix(self):
        s = stats.summarise([row(0, rad=0.1, rad_src="live", cpm=17)])
        assert set(s["provenance_matrix"]) == {"position", "radiation"}


class TestNeverPooled:
    def test_mixed_tiers_get_separate_blocks(self):
        rows = [row(0, rad=1.0, rad_src="live", cpm=100),
                row(1, rad=3.0, rad_src="live", cpm=300),
                row(2, rad=10.0, rad_src="simulated", cpm=1000)]
        s = stats.summarise(rows)
        assert block(s, "dose_rate_usvh", "live")["stats"]["mean"] == pytest.approx(2.0)
        assert block(s, "dose_rate_usvh", "simulated")["stats"]["mean"] == pytest.approx(10.0)
        assert block(s, "dose_rate_usvh", "live")["stats"]["n"] == 2

    def test_reading_value_follows_reading_source_not_row(self):
        # Simulated position carrying a live PM reading: PM stats are LIVE.
        s = stats.summarise([row(0, pos="simulated", aq_src="live", pm25=12.0, pm10=20.0)])
        assert block(s, "pm25", "live")["stats"]["mean"] == 12.0
        assert block(s, "pm25", "simulated") is None


class TestModelledCpm:
    def test_modelled_cpm_omitted_dose_kept(self):
        s = stats.summarise([row(0, pos="modelled", rad=0.14, rad_src="modelled", cpm=46.8)])
        cpm = block(s, "cpm", "modelled")
        assert "stats" not in cpm and "back-calculated" in cpm["omitted"]
        assert block(s, "dose_rate_usvh", "modelled")["stats"]["n"] == 1

    def test_simulated_cpm_kept(self):
        s = stats.summarise([row(0, rad=0.1, rad_src="simulated", cpm=17)])
        assert block(s, "cpm", "simulated")["stats"]["mean"] == 17


class TestDescribe:
    def test_matches_postgres_definitions(self):
        # percentile_cont over 1,2,3,4: P50 2.5, P95 3.85, P99 3.97.
        # stddev_samp(1,2,3,4) = 1.2909944...
        d = stats.describe([4, 1, 3, 2])
        assert d["p50"] == pytest.approx(2.5)
        assert d["p95"] == pytest.approx(3.85)
        assert d["p99"] == pytest.approx(3.97)
        assert d["sd"] == pytest.approx(1.2909944487)
        assert (d["min"], d["max"], d["mean"]) == (1, 4, 2.5)

    def test_single_value_has_no_sd(self):
        assert stats.describe([5.0])["sd"] is None

    def test_null_values_counted_not_averaged(self):
        s = stats.summarise([row(0, aq_src="live", pm25=10.0),
                             row(1, aq_src="live", pm25=None)])
        b = block(s, "pm25", "live")
        assert b["stats"]["n"] == 1 and b["null_count"] == 1


class TestSummary:
    def test_citations_distinct_over_many_rows_sharing_one(self):
        # The F10.3 CP0 regression shape: many rows, ONE shared note.
        rows = [row(i, note="KNRA Table 3.1") for i in range(50)]
        rows.append(row(50, note=""))
        assert stats.summarise(rows)["citations"] == ["KNRA Table 3.1"]

    def test_window_from_timestamps(self):
        s = stats.summarise([row(5), row(0), row(9)])
        assert s["window_start"] == T0.isoformat()
        assert s["window_end"] == (T0 + timedelta(seconds=9)).isoformat()
        assert s["row_count"] == 3
# ─── RANGER V3 END: 16-report-stats ───
