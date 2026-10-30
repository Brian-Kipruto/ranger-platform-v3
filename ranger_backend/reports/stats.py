# ─── RANGER V3 START: 16-report-stats ───
"""
Report arithmetic (F16 fork 7). Pure functions over plain rows: no ORM, no I/O,
so every rule here is tested directly.

Rules
-----
1. Each reading is labelled by ITS OWN source, never its row's (ADR-0020).
   The row's `source` labels the position only.
2. Stats are NEVER pooled across tiers. A mean over live and simulated values
   describes nothing that exists. A kind with readings in two tiers gets two
   stats rows.
3. The report's headline provenance is the WEAKEST tier present across
   positions and every reading kind — never the majority. One simulated
   reading in ten thousand live ones still makes the report "contains
   simulated data".
4. Modelled radiation reports dose rate only. Its CPM is back-calculated from
   the published dose rate (core.marsabit.CPM_PER_USVH) — a derived number,
   not data — so it is not summarised at all.

Statistics definitions match PostgreSQL so a psql query can check them:
  sd   = sample SD (ddof=1)          = stddev() / stddev_samp()
  Pxx  = linear interpolation        = percentile_cont(xx/100)
"""
import numpy as np

from core.models import SensorLog

# TextChoices iterate in declaration order: most -> least authoritative.
TIERS = [s.value for s in SensorLog.Source]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# The value columns each statistics block reads, in the order printed.
# (kind, quantity key, row column, unit, label, decimals printed)
QUANTITIES = [
    ("radiation", "dose_rate_usvh", "radiation_data__dose_rate_usvh", "µSv/h", "Dose rate", 4),
    ("radiation", "cpm", "radiation_data__radiation_value", "CPM", "Count rate", 1),
    ("air_quality", "pm25", "air_quality_data__pm25", "µg/m³", "PM2.5", 1),
    ("air_quality", "pm10", "air_quality_data__pm10", "µg/m³", "PM10", 1),
]

# Every reading kind and the column holding its own source. `position` is the
# row's source (ADR-0020: it labels the fix).
KIND_SOURCE_COLUMN = {
    "position": "source",
    "radiation": "radiation_data__source",
    "air_quality": "air_quality_data__source",
    "imu_baro": "imu_baro_data__source",
}

# Rule 4: (kind, quantity) pairs that are derived, not data, in a given tier.
OMITTED = {
    (SensorLog.Source.MODELLED.value, "cpm"):
        "Count rate omitted: back-calculated from the published dose rate, "
        "not a measurement.",
}

# The .values() list every caller must fetch. One LEFT-JOINed query.
ROW_COLUMNS = [
    "timestamp", "source", "provenance_note",
    *(c for c in KIND_SOURCE_COLUMN.values() if c != "source"),
    *(q[2] for q in QUANTITIES),
]


def weakest(tiers) -> str | None:
    """The least authoritative tier in `tiers`, or None if empty."""
    present = [t for t in tiers if t is not None]
    if not present:
        return None
    return max(present, key=lambda t: TIER_RANK[t])


def describe(values) -> dict:
    """n/min/max/mean/sd/p50/p95/p99 with PostgreSQL's definitions."""
    a = np.asarray(values, dtype=np.float64)
    n = int(a.size)
    if n == 0:
        return {"n": 0}
    p50, p95, p99 = np.percentile(a, [50, 95, 99], method="linear")
    return {
        "n": n,
        "min": float(a.min()),
        "max": float(a.max()),
        "mean": float(a.mean()),
        "sd": float(a.std(ddof=1)) if n > 1 else None,
        "p50": float(p50),
        "p95": float(p95),
        "p99": float(p99),
    }


def provenance_matrix(rows) -> dict:
    """{kind: {tier: count}} for every kind present, tiers in rank order."""
    matrix = {}
    for kind, col in KIND_SOURCE_COLUMN.items():
        counts = {t: 0 for t in TIERS}
        for r in rows:
            t = r.get(col)
            if t is not None:
                counts[t] += 1
        if any(counts.values()):
            matrix[kind] = counts
    return matrix


def quantity_stats(rows) -> list[dict]:
    """One block per (quantity, tier) with data. Never pooled (rule 2)."""
    blocks = []
    for kind, key, col, unit, label, decimals in QUANTITIES:
        source_col = KIND_SOURCE_COLUMN[kind]
        by_tier = {t: [] for t in TIERS}
        nulls = {t: 0 for t in TIERS}
        for r in rows:
            tier = r.get(source_col)
            if tier is None:
                continue  # no reading of this kind on the row
            v = r.get(col)
            if v is None:
                nulls[tier] += 1
            else:
                by_tier[tier].append(v)
        for tier in TIERS:
            if not by_tier[tier] and not nulls[tier]:
                continue
            block = {
                "kind": kind, "quantity": key, "label": label, "unit": unit,
                "decimals": decimals,
                "source": tier, "null_count": nulls[tier],
            }
            omitted = OMITTED.get((tier, key))
            if omitted:
                block["omitted"] = omitted
            else:
                block["stats"] = describe(by_tier[tier])
            blocks.append(block)
    return blocks


def summarise(rows) -> dict:
    """Everything the report prints, JSON-serialisable (stored on Report)."""
    matrix = provenance_matrix(rows)
    present = [t for counts in matrix.values() for t, n in counts.items() if n]
    timestamps = [r["timestamp"] for r in rows]
    # Distinct in Python, not SQL: .distinct() on an ordered queryset adds the
    # ordering column to the SELECT and returns every row (F10.3 CP0 bug).
    notes = sorted({r["provenance_note"] for r in rows if r["provenance_note"]})
    return {
        "row_count": len(rows),
        "weakest_source": weakest(present),
        "provenance_matrix": matrix,
        "position_sources": [t for t, n in matrix.get("position", {}).items() if n],
        "window_start": min(timestamps).isoformat() if timestamps else None,
        "window_end": max(timestamps).isoformat() if timestamps else None,
        "citations": notes,
        "quantities": quantity_stats(rows),
    }
# ─── RANGER V3 END: 16-report-stats ───
