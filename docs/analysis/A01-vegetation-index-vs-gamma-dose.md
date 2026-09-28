# A01 — Do satellite vegetation indices explain gamma dose variance at the Marsabit survey sites?

*Date: 2026-08-08*
*Feature: F10.3*
*Command: `python manage.py analyze_covariance`*
*Answer: **no**, at least not across sites on a single date.*

---

## Why this matters beyond one hypothesis

RANGER's purpose is ground-truth infrastructure for Earth Observation: EO
products over African drylands are inverted through models whose coefficients
were validated where the ground stations are, and Kenya has fewer than one
validated station per 10,000 km² of rangeland.

So a result of this shape — *a satellite-derived proxy tested against ground
measurement in an under-instrumented landscape, and failing* — is not a
setback. It is the function working. The proxy is not wrong everywhere; it is
wrong here, and nobody could have known that without measuring here.

## Why we asked

The F10 epic's stated premise is that satellite EO **explains and contextualizes**
ground radiological variability, and ground data validates satellite surface
products. The mechanism proposed for that was soil-water attenuation: water in
the top soil layer absorbs terrestrial gamma, so wetter, more vegetated ground
should read *lower* dose rates.

That predicts a **negative** relationship between vegetation index and gamma
dose rate. It is a real physical effect and it is well documented. The question
is whether it dominates at these seven sites.

Asserting it without checking would have been the single most fragile claim in
the pitch — one informed question away from collapse.

## Method

For each of the seven KNRA survey sites we hold one Sentinel-2 SR Harmonized
scene (5 Aug 2026, ≤10% cloud), clipped to the site AOI plus a 500 m buffer,
stored as a validated COG in EPSG:4326.

For each clip:

- **NDVI** = (B8−B4)/(B8+B4)
- **BSI** = ((B11+B4)−(B8+B2))/((B11+B4)+(B8+B2))

Both are normalised ratios over Sentinel-2, whose calibration is purely
multiplicative, so the reflectance scale cancels exactly and raw DNs are
correct. (This is *not* true of Landsat Collection 2, whose additive offset
does not cancel — see ADR-0013.)

We take the **median** over valid pixels per site — median rather than mean
because these distributions are skewed by a small number of vegetated pixels
along drainage.

Dose rates are the **site means published in the KNRA report, Table 3.1**.
These are real in-situ measurements, not our modelled points.

Association is measured by **Spearman rank correlation** across the seven
sites, chosen over Pearson because we have no reason to expect the
relationship to be linear and n is small.

## Result

| Site | Dose rate (nSv/h) | NDVI median | BSI median | Valid px |
|---|---|---|---|---|
| Boji | 46 ± 30 | 0.055 | 0.188 | 19,126 |
| Kargi (Sirius) | 55 ± 31 | 0.123 | 0.248 | 12,656 |
| Dukana W1 | 73 ± 36 | 0.087 | 0.163 | 12,543 |
| Gamura | 79 ± 37 | 0.066 | 0.161 | 14,384 |
| Dukana W2 | 82 ± 36 | 0.083 | 0.159 | 11,877 |
| Balesa (control) | 87 ± 50 | 0.073 | 0.199 | 13,924 |
| Forole | 140 ± 78 | 0.131 | 0.254 | 13,328 |

```
dose vs NDVI   rho = +0.393   n = 7   |rho| needed for p<0.05 = 0.786
dose vs BSI    rho = +0.179   n = 7   |rho| needed for p<0.05 = 0.786
```

**Neither index explains the variance.** Both correlations are weak, and both
are *positive* — the opposite sign to the attenuation hypothesis.

The clearest way to see there is nothing to find: the two highest-NDVI sites
are **Kargi (0.123, dose 55)** and **Forole (0.131, dose 140)** — the second
lowest and the highest dose rates in the survey. Essentially the same
vegetation index at a 2.5× difference in gamma.

## What we think is actually going on

NDVI and BSI track *each other* rather than dose. Kargi and Forole carry the
two highest BSI values (0.248, 0.254) while the other five sit between 0.159
and 0.199. Two indices agreeing on the same two sites, and neither agreeing
with dose rate, says they are both responding to a surface property that is
not radiological.

The likely shared driver is **lithology**. From the report's own soil
chemistry (Tables 3.2, 3.6):

| | ⁴⁰K (Bq/kg) | K (w%) | Zr (ppm) |
|---|---|---|---|
| Forole | 858–878 | 4.07–4.21 | 1032–2185 |
| Boji | 89–133 | 0.58–1.56 | 197–264 |

Forole's soil carries roughly **seven times** Boji's ⁴⁰K. Gamma dose at these
sites is dominated by the potassium content of the parent material, and the
report reaches the same conclusion independently — it attributes Forole's
elevation to geogenic enrichment and heavy-mineral or volcanic-derived
sediments, not to contamination.

Weathered potassium-rich volcanics also retain more moisture and support more
vegetation than the surrounding lava plain and salt flats. So vegetation and
gamma both rise with the same geology, which would produce exactly the weak
positive association we observe, and would swamp an attenuation effect
operating in the other direction.

**Soil moisture attenuation is not disproved by this.** It is a within-site,
within-season effect competing here against a between-site geological signal
an order of magnitude larger. Testing it properly needs the moisture term
measured, not inferred from vegetation.

## What this analysis cannot show

Stated plainly because the numbers above are easy to over-read.

1. **n = 7.** Spearman needs |rho| ≥ 0.786 for significance at this sample
   size. Even a strong-looking result here would be weak evidence, and this
   one is not strong-looking.
2. **One date.** Every scene is the 5 Aug 2026 pass. NDVI in an arid system
   swings hard with recent rainfall. A relationship absent on one date is not
   absent in general.
3. **One number per site on each axis.** This compares site medians against
   site means. It says nothing about *within-site* spatial correlation, which
   is the form the claim would actually need to take.
4. **Our 12,081 ground points are MODELLED, not measured.** Their values are
   drawn to reproduce the report's published statistics; their positions are
   synthetic. They were not used here and must not be used for correlation —
   see the warning below.

## Consequence for F10.4

**The correlation engine must refuse to consume `modelled` or `simulated`
rows.**

A per-pixel join between real imagery and our modelled points would correlate
genuine satellite pixels against generated coordinates. The output would look
like a finding and would be an artefact of the point generator. The
`SensorLog.source` tier already records the distinction; F10.4 has to *act* on
it rather than merely carry it.

Correlation is computed against `live` and `reported` tiers only. Anything
else is a visualisation, not an analysis.

## Reproducing

```bash
cd $R/ranger_backend
python manage.py analyze_covariance
python manage.py analyze_covariance --csv /tmp/covariance.csv
```

The command prints the significance threshold beside the correlation, and
warns explicitly when rho comes out positive, so the result cannot be read
without its context.

## The finding, in one sentence

*Across seven KNRA survey sites on a single Sentinel-2 date, vegetation and
bare-soil indices do not explain gamma dose-rate variance (rho = 0.39 and 0.18,
n = 7, neither significant); the variance appears to be lithological, and the
soil-moisture hypothesis needs a moisture measurement — Sentinel-1 SAR
backscatter at 10 m — rather than a vegetation proxy.*
