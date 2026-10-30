# ─── RANGER V3 START: 16-csv-export ───
"""
The SensorLog CSV format, in one place.

Two consumers write it: GET /api/data-logs/export/ and the compliance report,
which embeds the mission's full data in the PDF (F16 fork 8). They must never
disagree on a column, so neither owns the format: both call this.

The header is pinned by core/tests.py (EXPECTED_CSV_HEADER). Changing
CSV_FIELDNAMES fails that test on purpose.
"""
import csv

from .serializers import DataLogSerializer

CSV_FIELDNAMES = [
    "id", "robot_id", "robot_id_str", "robot_name", "mission_id", "mission_name",
    "timestamp", "latitude", "longitude",
    # F10.2: provenance travels with every exported row. An export that
    # loses its labels is exactly how modelled data gets mistaken for
    # measured data downstream.
    "source", "provenance_note",
    # F13 (ADR-0020): each reading group ends with its own source column.
    # `source` above is the position's; a reader of radiation_value must
    # read radiation_source.
    "radiation_value", "dose_rate_usvh", "radiation_source",
    "pm25", "pm10", "air_quality_source",
    "roll", "pitch", "yaw", "pressure_baro", "altitude_baro", "imu_source",
]


def write_sensor_log_csv(stream, queryset) -> int:
    """Write `queryset` to `stream` as CSV. Returns the number of data rows.

    The caller owns ordering and scoping. The serializer is reused so CSV
    cells and JSON rows agree exactly (same null-safe reading access).
    """
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    n = 0
    for row in DataLogSerializer(queryset, many=True).data:
        writer.writerow(row)
        n += 1
    return n
# ─── RANGER V3 END: 16-csv-export ───
