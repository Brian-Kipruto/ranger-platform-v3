# ─── RANGER V3 START: covariance analysis ───
"""
Per-site satellite index statistics against published gamma dose rates.

    python manage.py analyze_covariance
    python manage.py analyze_covariance --dataset s2 --csv out.csv

WHAT THIS IS
------------
A descriptive comparison, not an inference. For each KNRA survey site with a
COG on disk it computes median NDVI and BSI over the clip, puts them beside
the dose rate the report publishes for that site (Table 3.1), and reports a
Spearman rank correlation across sites.

WHAT THIS IS NOT
----------------
Evidence of a mechanism, and — at n=7 — barely evidence of anything. Seven
points is enough to see a direction and nowhere near enough to establish one.
Spearman on seven pairs needs |rho| > 0.79 for p < 0.05 two-tailed, and the
command prints that threshold next to the result so the number cannot be read
without its context.

Two further limits, stated because they change how the output should be read:

1. **The dose rates are site MEANS from the report, not per-pixel values.**
   This compares one number per site against one number per site. It cannot
   say anything about within-site spatial correlation, which is what would
   actually demonstrate a covariate relationship. That needs F10.4's
   correlation join against the point data.

2. **One date.** Every scene is a single pass. NDVI in an arid system varies
   enormously with rainfall, so a relationship visible on one date may not
   hold on another — and its absence on one date does not disprove one.

WHY IT EXISTS ANYWAY
--------------------
Because the alternative is asserting a correlation on stage without having
looked at it. The pitch's core claim is that soil moisture attenuates
terrestrial gamma, which predicts MORE vegetation with LESS gamma. If the
data shows the opposite sign, that is far better known beforehand — and there
is a good geological reason it might: Forole's soil carries 868 Bq/kg of
40-K and 4.2% potassium against Boji's 126 Bq/kg, so gamma across these sites
may be dominated by lithology rather than moisture, with vegetation tracking
the same weathered volcanics rather than attenuating them.
"""
from __future__ import annotations

import csv as csv_module
import math

from django.core.management.base import BaseCommand, CommandError

from core.marsabit import SITES_BY_CODE
from satellite_integration import cog
from satellite_integration.models import SatelliteImage

# Indices computed here. Both are normalised ratios over Sentinel-2, so the
# reflectance scale cancels and raw DNs are correct — see render.py for why
# that is true of S2 and false of Landsat.
NDVI_BANDS = ("B8", "B4")
BSI_BANDS = ("B11", "B4", "B8", "B2")


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho, computed as Pearson on ranks. Ties averaged."""
    n = len(xs)
    if n < 3:
        return None

    def rank(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = shared
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(
        sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)
    )
    return num / den if den else None


# Two-tailed critical |rho| for p < 0.05, small n. Beyond the table, fall back
# to the normal approximation.
_RHO_CRIT = {5: 1.00, 6: 0.886, 7: 0.786, 8: 0.738, 9: 0.700, 10: 0.648}


def _critical_rho(n: int) -> float:
    if n in _RHO_CRIT:
        return _RHO_CRIT[n]
    return 1.96 / math.sqrt(max(n - 1, 1))


class Command(BaseCommand):
    help = (
        "Compare per-site satellite index medians against the dose rates "
        "published in the KNRA report. Descriptive only; see the module "
        "docstring for what it cannot show."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset", default="s2",
            help="Dataset code to analyse. Default s2 — mixing resolutions "
                 "across sites would compare 10 m against 30 m clips.",
        )
        parser.add_argument("--org", default="knra")
        parser.add_argument(
            "--csv", default=None,
            help="Also write the per-site table to this path.",
        )

    def handle(self, *args, **options):
        try:
            import numpy as np
            import rasterio
        except ImportError as exc:  # pragma: no cover
            raise CommandError(f"numpy and rasterio are required: {exc}")

        images = (
            SatelliteImage.objects
            .filter(
                dataset__code=options["dataset"],
                query__organization__slug=options["org"],
            )
            .exclude(cog_path="")
            .select_related("query", "query__mission", "dataset")
            .order_by("acquisition_date")
        )
        if not images:
            raise CommandError(
                f"No {options['dataset']} scenes on disk for org "
                f"{options['org']!r}. Run fetch_scenes first."
            )

        rows = []
        for image in images:
            site = self._site_for(image)
            if site is None:
                self.stdout.write(self.style.WARNING(
                    f"  skipping image {image.pk}: no matching KNRA site"
                ))
                continue

            path = cog.absolute_cog_path(image.cog_path)
            if not path.exists():
                self.stdout.write(self.style.WARNING(
                    f"  skipping {site['code']}: COG missing on disk"
                ))
                continue

            with rasterio.open(path) as src:
                names = [
                    src.descriptions[i] or f"band{i + 1}"
                    for i in range(src.count)
                ]

                def band(label):
                    if label not in names:
                        return None
                    return src.read(names.index(label) + 1).astype("float64")

                bands = {b: band(b) for b in set(NDVI_BANDS + BSI_BANDS)}

            ndvi = self._ratio(np, bands, NDVI_BANDS)
            bsi = self._bsi(np, bands)

            rows.append({
                "code": site["code"],
                "name": site["name"],
                "dose": site["mean"],
                "dose_sd": site["sd"],
                "ndvi": ndvi,
                "bsi": bsi,
                "px": int(np.isfinite(ndvi).sum()) if ndvi is not None else 0,
            })

        if not rows:
            raise CommandError("No site matched a scene on disk.")

        rows.sort(key=lambda r: r["dose"])
        self._report(rows)
        if options["csv"]:
            self._write_csv(rows, options["csv"])

    # ── helpers ──────────────────────────────────────────────────────

    def _site_for(self, image):
        """Match a scene back to its KNRA site.

        The clip's AOI key is in the cog_path (`..__<site>.tif`, F10.3 CP5).
        Scenes written before that layout fall back to the query label, then
        to the mission name.
        """
        stem = image.cog_path.rsplit("/", 1)[-1]
        if "__" in stem:
            code = stem.rsplit("__", 1)[-1].removesuffix(".tif")
            if code in SITES_BY_CODE:
                return SITES_BY_CODE[code]
        label = (image.query.label or "").lower()
        for code, site in SITES_BY_CODE.items():
            if label.startswith(code):
                return site
        name = (image.query.mission.name if image.query.mission_id else "") or ""
        for site in SITES_BY_CODE.values():
            if site["name"].lower() in name.lower() or name.lower() in site["name"].lower():
                return site
        return None

    def _ratio(self, np, bands, labels):
        a, b = bands.get(labels[0]), bands.get(labels[1])
        if a is None or b is None:
            return None
        with np.errstate(invalid="ignore", divide="ignore"):
            out = (a - b) / (a + b)
        return np.clip(out, -1.0, 1.0)

    def _bsi(self, np, bands):
        needed = [bands.get(b) for b in BSI_BANDS]
        if any(x is None for x in needed):
            return None
        swir_red = needed[0] + needed[1]
        nir_blue = needed[2] + needed[3]
        with np.errstate(invalid="ignore", divide="ignore"):
            out = (swir_red - nir_blue) / (swir_red + nir_blue)
        return np.clip(out, -1.0, 1.0)

    def _median(self, field):
        if field is None:
            return None
        import numpy as np
        valid = field[np.isfinite(field)]
        return float(np.median(valid)) if valid.size else None

    def _report(self, rows):
        import numpy as np  # noqa: F401  (kept for symmetry with _median)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Per-site index medians vs published dose rate (report Table 3.1)"
        ))
        self.stdout.write(
            f"  {'site':<12}{'dose nSv/h':>12}{'NDVI':>10}{'BSI':>10}"
            f"{'px':>10}"
        )
        self.stdout.write("  " + "-" * 54)

        doses, ndvis, bsis = [], [], []
        for r in rows:
            ndvi_m = self._median(r["ndvi"])
            bsi_m = self._median(r["bsi"])
            self.stdout.write(
                f"  {r['code']:<12}"
                f"{r['dose']:>7.0f} ± {r['dose_sd']:<3.0f}"
                f"{(f'{ndvi_m:.3f}' if ndvi_m is not None else '—'):>10}"
                f"{(f'{bsi_m:.3f}' if bsi_m is not None else '—'):>10}"
                f"{r['px']:>10,}"
            )
            if ndvi_m is not None:
                doses.append(r["dose"])
                ndvis.append(ndvi_m)
                bsis.append(bsi_m if bsi_m is not None else float("nan"))

        n = len(doses)
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Rank correlation across sites"))

        rho_ndvi = _spearman(doses, ndvis)
        crit = _critical_rho(n)
        if rho_ndvi is None:
            self.stdout.write("  too few sites to correlate")
        else:
            verdict = (
                "SIGNIFICANT at p<0.05" if abs(rho_ndvi) >= crit
                else "NOT significant at p<0.05"
            )
            self.stdout.write(
                f"  dose vs NDVI   rho = {rho_ndvi:+.3f}   n = {n}   "
                f"|rho| needed = {crit:.3f}   {verdict}"
            )
            if not any(math.isnan(b) for b in bsis):
                rho_bsi = _spearman(doses, bsis)
                self.stdout.write(
                    f"  dose vs BSI    rho = {rho_bsi:+.3f}   n = {n}   "
                    f"|rho| needed = {crit:.3f}"
                )

        self.stdout.write("")
        if rho_ndvi is not None and rho_ndvi > 0:
            self.stdout.write(self.style.WARNING(
                "  NOTE: rho is POSITIVE — more vegetation goes with MORE\n"
                "  gamma, the opposite of what soil-water attenuation\n"
                "  predicts. Consider lithology as the shared driver: the\n"
                "  report puts Forole at 868 Bq/kg 40-K and 4.2% K against\n"
                "  Boji's 126 Bq/kg. Potassium-rich weathered volcanics are\n"
                "  both more radioactive and better at holding vegetation."
            ))
        self.stdout.write(
            "  Descriptive only. One date, one median per site, n small.\n"
            "  Site means come from the report; per-pixel correlation needs\n"
            "  F10.4's join against the point data."
        )
        self.stdout.write("")

    def _write_csv(self, rows, path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv_module.DictWriter(
                fh,
                fieldnames=["code", "name", "dose_nsv_h", "dose_sd",
                            "ndvi_median", "bsi_median", "valid_px"],
            )
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "code": r["code"],
                    "name": r["name"],
                    "dose_nsv_h": r["dose"],
                    "dose_sd": r["dose_sd"],
                    "ndvi_median": self._median(r["ndvi"]),
                    "bsi_median": self._median(r["bsi"]),
                    "valid_px": r["px"],
                })
        self.stdout.write(self.style.SUCCESS(f"  wrote {path}"))
# ─── RANGER V3 END: covariance analysis ───
