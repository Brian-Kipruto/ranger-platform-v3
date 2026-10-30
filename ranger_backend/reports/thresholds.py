# ─── RANGER V3 START: 16-report-thresholds ───
"""
Reference levels the compliance report cites (F16 fork 3).

Every entry carries its citation. A bare number is not regulator-grade, and
neither is a number checked against the wrong quantity, so each entry also
says HOW it may be used:

  exceedance  per-reading comparison: count above, and (for non-modelled
              tiers) a list of the readings above.
  mean_only   the survey mean is set beside the level, the averaging mismatch
              stated, and nothing more. WHO PM levels are 24-hour means; a
              survey lasts minutes. No per-reading comparison.
  context     shown for orientation, never compared. Different quantity.

Language rule: no PASS/FAIL anywhere. Readings are "above" or "below" a
level, and each level states its kind. Nothing here is called a limit
unless it legally is one; none of these are.

Bump REGISTRY_VERSION whenever an entry changes. It is printed in the report
and stored on the Report, so any report says which registry it used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from core.models import SensorLog

REGISTRY_VERSION = "2026-10-30"

EXCEEDANCE, MEAN_ONLY, CONTEXT = "exceedance", "mean_only", "context"

# A per-reading list for MODELLED data would present placed positions and
# times as located anomalies. Modelled tiers get the count and fraction only.
NO_LIST_TIERS = {SensorLog.Source.MODELLED.value}
LIST_CAP = 25


@dataclass(frozen=True)
class Reference:
    key: str
    quantity: str          # stats quantity key this applies to
    value: float           # in `unit`
    unit: str
    kind: str              # "investigation level" | "guideline" | "background"
    use: str               # EXCEEDANCE | MEAN_ONLY | CONTEXT
    averaging: str
    citation: str
    url: str = ""
    note: str = ""


REFERENCES = [
    Reference(
        key="knra-marsabit-investigation",
        quantity="dose_rate_usvh",
        value=0.300,
        unit="µSv/h",
        kind="investigation level",
        use=EXCEEDANCE,
        averaging="individual reading",
        citation=(
            "Kenya Nuclear Regulatory Authority, Radiological and Geochemical "
            "Assessment of Former Oil Exploration Sites in Marsabit County, "
            "Kenya (April 2026), Table 2.2: ambient dose rate above 300 nSv/h "
            "classified as localized anomaly (investigate)"
        ),
    ),
    Reference(
        key="unscear-2000-outdoor-terrestrial",
        quantity="dose_rate_usvh",
        value=59.0,
        unit="nGy/h",
        kind="background",
        use=CONTEXT,
        averaging="population-weighted world average, outdoors",
        citation=(
            "UNSCEAR 2000 Report to the General Assembly, Vol. I, Annex B "
            "(Exposures from natural radiation sources)"
        ),
        note=(
            "Absorbed dose rate in air from terrestrial radionuclides only. A "
            "different quantity from the dose rate reported here (Gy, not Sv) "
            "and excluding the cosmic component, so it is context, not a "
            "comparison."
        ),
    ),
    Reference(
        key="who-2021-pm25-24h",
        quantity="pm25",
        value=15.0,
        unit="µg/m³",
        kind="guideline",
        use=MEAN_ONLY,
        averaging="24-hour mean, 99th percentile (3–4 exceedance days per year)",
        citation=(
            "WHO global air quality guidelines (2021), Table 3.26, "
            "ISBN 9789240034228"
        ),
        url="https://iris.who.int/handle/10665/345329",
    ),
    Reference(
        key="who-2021-pm10-24h",
        quantity="pm10",
        value=45.0,
        unit="µg/m³",
        kind="guideline",
        use=MEAN_ONLY,
        averaging="24-hour mean, 99th percentile (3–4 exceedance days per year)",
        citation=(
            "WHO global air quality guidelines (2021), Table 3.26, "
            "ISBN 9789240034228"
        ),
        url="https://iris.who.int/handle/10665/345329",
    ),
]

# Stated in the report so a reader knows they were considered, not forgotten.
NOT_COMPARED = [
    "The annual public effective-dose limit is not compared. It applies to "
    "an annual effective dose; converting a survey dose rate to it needs an "
    "occupancy assumption this report does not make.",
    "Count rate (CPM) is not compared with any level. Counts depend on the "
    "detector and have no dose meaning without a calibration.",
]


def resolving_decimals(value: float, level: float, decimals: int, cap: int = 4) -> int:
    """Fewest decimals (>= `decimals`) at which `value` and `level` print
    differently. A survey mean of 14.96 printed as "15.0, below the 15.0
    guideline" contradicts itself on the page; at 2 decimals it reads 14.96.
    Stops at `cap`; a value equal to the level is printed as equal."""
    d = decimals
    while d < cap and round(value, d) == round(level, d) and value != level:
        d += 1
    return d


def references_for(quantity: str) -> list[Reference]:
    return [r for r in REFERENCES if r.quantity == quantity]


def compare(summary: dict, points: list[dict]) -> dict:
    """Comparisons for every stats block that has a reference.

    `summary` is stats.summarise(...) output; `points` carry the per-reading
    columns (dose_rate_usvh + radiation_source, pm25/pm10 +
    air_quality_source, lon, lat, timestamp) for exceedance lists.
    """
    rows = []
    lists = []
    window_s = summary.get("window_seconds")
    for block in summary["quantities"]:
        if "stats" not in block or not block["stats"].get("n"):
            continue
        for ref in references_for(block["quantity"]):
            if ref.use == CONTEXT:
                continue
            s = block["stats"]
            row = {
                "ref": ref.key, "quantity": block["quantity"],
                "label": block["label"], "unit": ref.unit,
                "decimals": block["decimals"], "source": block["source"],
                "value": ref.value, "kind": ref.kind, "use": ref.use,
                "averaging": ref.averaging,
            }
            if ref.use == EXCEEDANCE:
                kind_col = f"{block['kind']}_source"  # the reading's OWN source
                above = [p for p in points
                         if p.get(kind_col) == block["source"]
                         and p.get(block["quantity"]) is not None
                         and p[block["quantity"]] > ref.value]
                row.update(n=s["n"], n_above=len(above),
                           pct_above=100.0 * len(above) / s["n"],
                           max=s["max"])
                if above and block["source"] not in NO_LIST_TIERS:
                    above.sort(key=lambda p: p[block["quantity"]], reverse=True)
                    lists.append({
                        "ref": ref.key, "label": block["label"], "unit": ref.unit,
                        "decimals": block["decimals"], "source": block["source"],
                        "level": ref.value, "total": len(above),
                        "rows": [{
                            "timestamp": p["timestamp"].strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "lat": p["lat"], "lon": p["lon"],
                            "value": p[block["quantity"]],
                        } for p in above[:LIST_CAP]],
                    })
                elif above:
                    row["list_withheld"] = (
                        "No per-reading list: these readings are MODELLED, so "
                        "their positions and times are placed, not measured."
                    )
            else:  # MEAN_ONLY
                row.update(mean=s["mean"], mean_above=s["mean"] > ref.value,
                           mean_decimals=resolving_decimals(
                               s["mean"], ref.value, block["decimals"]),
                           window_seconds=window_s)
            rows.append(row)

    context = [asdict(r) for r in REFERENCES if r.use == CONTEXT
               and any(b["quantity"] == r.quantity and "stats" in b
                       for b in summary["quantities"])]
    cited = sorted({r.citation for r in REFERENCES
                    if r.key in {x["ref"] for x in rows}
                    or r.key in {c["key"] for c in context}})
    return {
        "registry_version": REGISTRY_VERSION,
        "rows": rows,
        "exceedance_lists": lists,
        "context": context,
        "not_compared": NOT_COMPARED,
        "citations": cited,
    }
# ─── RANGER V3 END: 16-report-thresholds ───
