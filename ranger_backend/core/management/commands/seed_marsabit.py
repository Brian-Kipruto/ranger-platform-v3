# ─── RANGER V3 START: seed_marsabit ───
"""
Seeds Marsabit ground-survey data (F10.2 CP3).

Creates, for the KNRA tenant:
  * Organization  knra
  * Robots        KNRA-PGIS-2-1 (NaI scintillation), KNRA-BGEIGIE-NANO
                  — the instruments ARE the sensing platforms; SensorLog.robot
                    is non-null, and inventing a fake rover would be a worse
                    lie than modelling the detector as what it is
  * Missions      one per site, area_of_interest = the site polygon
                  (first real use of the field F10.1 added)
  * SensorLogs    ~12,081 points across 7 sites, ALL labelled MODELLED

Honesty contract
----------------
The raw survey logs are not available; only the published report. Every point
this command writes is generated to match the report's published per-site
statistics. The distribution is faithful. The individual points are not
measurements and are never labelled as such:

    source          = SensorLog.Source.MODELLED
    provenance_note = "Modelled from KNRA ... Table 3.1 (<site>, n=..., ...)"

If you ever find yourself wanting to relabel these `reported` or `live` to
make a demo look better, that is the moment the platform's whole claim stops
being true.

Volume
------
Full published n by default (~12,081 rows). That is deliberately realistic:
the PGIS-2-1 logged >20,000 readings over five days, so a return visit to
Forole with a rover produces this order of magnitude. Seeding it now means the
map point cap, pagination, chart rendering, and the GiST index meet real load
here rather than in the field. Use --scale for faster dev iteration.
"""
import math
import random
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Organization
from core.geo import point_from_latlon, polygon_from_bbox
from core.marsabit import (
    BGEIGIE_INTERVAL_S,
    CITATION,
    CPM_PER_USVH,
    PGIS_INTERVAL_S,
    SITES,
    SURVEY_START,
)
from core.models import RadiationLog, Robot, SensorLog, SensorType
from missions.models import Mission

# Report Table 2.2: >300 nSv/h is classified "localized anomaly (investigate)".
ANOMALY_THRESHOLD = 300.0

ORG_SLUG = "knra"
ORG_NAME = "Kenya Nuclear Regulatory Authority"

INSTRUMENTS = [
    {
        "robot_id_str": "KNRA-PGIS-2-1",
        "name": "PGIS-2-1 NaI(Tl) Scintillation Detector",
        "interval_s": PGIS_INTERVAL_S,
    },
    {
        "robot_id_str": "KNRA-BGEIGIE-NANO",
        "name": "bGeigie Nano Geiger-Muller Counter",
        "interval_s": BGEIGIE_INTERVAL_S,
    },
]


def sample_dose_rates(rng, n, mean, sd, lo, hi, skew):
    """Generate n dose rates matching a published summary.

    Approach: lognormal body (which gives the right-skewed shape every site
    shows), affine-corrected so the sample mean and SD land on the published
    values, then clipped to [lo, hi].

    For strongly skewed sites (Forole: skew 10, kurtosis 105, isolated
    readings past 1 uSv/h) the lognormal body alone will not reach the
    published maximum, so a small tail fraction is drawn between the anomaly
    threshold and hi. That tail is the *point* at Forole — a generated cloud
    without it would misrepresent the site as unremarkable.

    Honest about its limits: mean, SD, min and max are matched closely; skew
    is approximated; kurtosis is not fitted at all.
    """
    if n <= 0:
        return []

    # Split the published SD between body and tail. At high skew the SD is
    # INFLATED by a few extreme outliers — the bulk is tighter than sd
    # suggests. Forcing the body to carry the full SD produces far too many
    # points above the 300 nSv/h anomaly threshold, which would misrepresent
    # Forole as broadly hot rather than background-with-isolated-anomalies.
    if skew >= 5:
        tail_fraction = 0.018
        body_sd_target = sd * 0.45
        # The tail also pulls the overall mean up, so the body must sit BELOW
        # the published mean for the combined sample to land on it.
        tail_mean = (ANOMALY_THRESHOLD + hi) / 2.0
        body_mean_target = (mean - tail_fraction * tail_mean) / (1 - tail_fraction)
    else:
        tail_fraction = 0.0
        body_sd_target = sd
        body_mean_target = mean

    n_tail = int(n * tail_fraction)
    n_body = n - n_tail

    sigma = math.sqrt(math.log(1.0 + (body_sd_target / body_mean_target) ** 2))
    mu = math.log(body_mean_target) - 0.5 * sigma ** 2

    values = [rng.lognormvariate(mu, sigma) for _ in range(n_body)]

    # Affine correction: lognormal sampling drifts off the target in small n.
    body_mean = sum(values) / len(values)
    body_sd = math.sqrt(sum((v - body_mean) ** 2 for v in values) / len(values)) or 1.0
    scale = body_sd_target / body_sd
    values = [body_mean_target + (v - body_mean) * scale for v in values]

    values = [min(max(v, lo), hi) for v in values]

    # Anomaly tail, drawn above the report's 300 nSv/h "localized anomaly"
    # threshold.
    values.extend(rng.uniform(ANOMALY_THRESHOLD, hi) for _ in range(n_tail))

    rng.shuffle(values)
    return values


class Command(BaseCommand):
    help = (
        "Seed Marsabit ground-survey data modelled from published KNRA "
        "statistics. All rows are labelled MODELLED."
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42,
                            help="RNG seed. Same seed = identical output.")
        parser.add_argument("--scale", type=float, default=1.0,
                            help="Fraction of published n to generate (0-1). "
                                 "Use ~0.05 for fast dev iteration.")
        parser.add_argument("--clear", action="store_true",
                            help="Delete existing KNRA-org SensorLogs first. "
                                 "Only touches the knra tenant.")
        parser.add_argument("--site", type=str, default=None,
                            help="Seed a single site by code, e.g. 'forole'.")

    @transaction.atomic
    def handle(self, *args, **options):
        scale = options["scale"]
        if not 0 < scale <= 1:
            raise CommandError("--scale must be in (0, 1]")

        rng = random.Random(options["seed"])
        self.stdout.write(self.style.WARNING(
            f"RNG seeded with {options['seed']} — output is reproducible."
        ))

        org, _ = Organization.objects.get_or_create(
            slug=ORG_SLUG,
            defaults={"name": ORG_NAME, "theme_color": "#0F766E"},
        )

        geiger, _ = SensorType.objects.get_or_create(
            code="geiger",
            defaults={"name": "Geiger Counter", "unit": "CPM"},
        )

        robots = {}
        for spec in INSTRUMENTS:
            robot, _ = Robot.objects.get_or_create(
                robot_id_str=spec["robot_id_str"],
                defaults={
                    "organization": org,
                    "name": spec["name"],
                    "metadata": {
                        "instrument": True,
                        "logging_interval_s": spec["interval_s"],
                        "source": CITATION,
                    },
                },
            )
            robot.installed_sensors.add(geiger)
            robots[spec["robot_id_str"]] = robot

        primary = robots["KNRA-PGIS-2-1"]

        if options["clear"]:
            deleted, _ = SensorLog.objects.filter(
                robot__organization=org
            ).delete()
            self.stdout.write(f"  cleared {deleted} existing KNRA rows")

        sites = SITES
        if options["site"]:
            sites = [s for s in SITES if s["code"] == options["site"]]
            if not sites:
                raise CommandError(f"unknown site: {options['site']}")

        # Each site gets its own day-slot inside the 1-5 July 2024 window, then
        # points march forward at the instrument's logging interval.
        total_written = 0
        for day_offset, site in enumerate(sites):
            written = self._seed_site(
                rng, org, primary, site, scale, day_offset % 5
            )
            total_written += written

        self.stdout.write(self.style.SUCCESS(
            f"\nseeded {total_written} MODELLED SensorLogs across "
            f"{len(sites)} Marsabit site(s) for org '{org.slug}'"
        ))
        self.stdout.write(
            "Provenance: modelled from published summary statistics. "
            "These are NOT measurements."
        )

    def _seed_site(self, rng, org, robot, site, scale, day_offset):
        n = max(1, int(site["n"] * scale))

        aoi = polygon_from_bbox(*site["bbox"])
        mission, _ = Mission.objects.get_or_create(
            organization=org,
            name=site["name"],
            defaults={
                "robot": robot,
                "status": Mission.Status.COMPLETED,
                "description": site["description"],
                "metadata": {"site_code": site["code"], "area": site["area"]},
            },
        )
        # Set separately so re-running updates the AOI if the bounds are
        # refined against real GPS later.
        mission.area_of_interest = aoi
        mission.save(update_fields=["area_of_interest"])

        values = sample_dose_rates(
            rng, n, site["mean"], site["sd"], site["min"], site["max"], site["skew"]
        )

        min_lon, min_lat, max_lon, max_lat = site["bbox"]
        start = datetime.combine(
            SURVEY_START + timedelta(days=day_offset), time(8, 0), dt_timezone.utc
        )
        note = (
            f"Modelled from {CITATION}, Table 3.1 "
            f"({site['name']}, n={site['n']}, mean={site['mean']} nSv/h, "
            f"SD={site['sd']})"
        )

        logs = []
        for i, dose_nsv in enumerate(values):
            logs.append(SensorLog(
                robot=robot,
                mission=mission,
                timestamp=start + timedelta(seconds=i * PGIS_INTERVAL_S),
                location=point_from_latlon(
                    lat=rng.uniform(min_lat, max_lat),
                    lon=rng.uniform(min_lon, max_lon),
                ),
                source=SensorLog.Source.MODELLED,
                provenance_note=note,
            ))
        SensorLog.objects.bulk_create(logs, batch_size=2000)

        readings = []
        for log, dose_nsv in zip(logs, values):
            dose_usvh = dose_nsv / 1000.0
            readings.append(RadiationLog(
                sensor_log=log,
                # Back-calculated from the published dose rate, not measured.
                radiation_value=round(dose_usvh * CPM_PER_USVH, 2),
                dose_rate_usvh=round(dose_usvh, 6),
            ))
        RadiationLog.objects.bulk_create(readings, batch_size=2000)

        mean = sum(values) / len(values)
        self.stdout.write(
            f"  {site['code']:<11} {len(logs):>6} pts  "
            f"mean {mean:6.1f} nSv/h (published {site['mean']:.0f})  "
            f"max {max(values):7.1f}"
        )
        return len(logs)
# ─── RANGER V3 END: seed_marsabit ───
