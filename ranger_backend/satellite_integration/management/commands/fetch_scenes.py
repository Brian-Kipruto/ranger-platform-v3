# ─── RANGER V3 START: fetch_scenes ───
"""Retrieve real satellite scenes over a Marsabit site (F10.2 CP5).

    manage.py fetch_scenes --site forole --dataset s2 \
        --start 2026-01-01 --end 2026-07-01 --max-cloud 10 --limit 3

What this command guarantees, and why each guarantee exists
-----------------------------------------------------------
1. THE AOI IS ALWAYS CLIPPED. A full Sentinel-2 tile is ~1 GB; the survey
   sites are 100-300 m across. Downloading a tile to look at a hectare would
   spend Community Tier quota at roughly a million to one.

2. THE FOOTPRINT IS READ OFF THE FILE. Earth Engine reports the footprint of
   the whole scene. What lands on disk is a clip of it. Storing the scene
   footprint would claim we hold imagery over ground we never downloaded, and
   every spatial query in F10.4 would inherit that.

3. THE INTERSECTION IS ASSERTED IN POSTGIS. Not in Python, and not by trusting
   `filterBounds`. If the geometry we stored does not actually intersect the
   AOI we asked for, something upstream is wrong and the query is marked
   FAILED rather than quietly recording a scene that is somewhere else.

4. `is_verified` MEANS A SCENE LANDED. `check_gee` proves a collection ID
   resolves; this command proves the collection actually yields a readable
   raster. Only the second is worth showing in the DATA PROVIDERS panel as
   "CONNECTED", so only this command sets the flag.

5. RAW VALUES, NO SCALE FACTORS. Sentinel-2 SR is scaled by 10000 and
   Landsat C2 L2 carries its own scale and offset. CP5 is retrieval, not
   science: applying corrections here would bury an assumption inside a
   download step. The COG records RANGER_VALUES=raw in its own metadata so
   F10.4 cannot miss it.
"""
from __future__ import annotations

import datetime as dt
import math

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization
from core.geo import polygon_from_bbox
from core.marsabit import SITES_BY_CODE
from missions.models import Mission
from satellite_integration import cog, gee_client
from satellite_integration.models import (
    SatelliteDataset,
    SatelliteImage,
    SatelliteQuery,
)

# Default context around a site. The bare bboxes are 100-300 m: at Sentinel-2's
# 10 m that is a 10-30 pixel square, which is correct and completely unreadable.
# 500 m of padding gives ~150x150 px — enough for a bare-soil index to have
# neighbours to compare against, and still three orders of magnitude under the
# download ceiling.
DEFAULT_BUFFER_M = 500.0

# Small on purpose. An exploratory run should not be able to spend an
# afternoon's EECU before anyone reads the first result.
DEFAULT_LIMIT = 3

_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON_EQUATOR = 111_320.0


def buffered_aoi(bbox: tuple[float, float, float, float], buffer_m: float):
    """Expand a site bbox by `buffer_m`, converting metres at the site's latitude.

    A fixed degree buffer would be ~11% wider in longitude at Kargi (2.6°N)
    than the equator figure implies. Small, but this is the polygon that gets
    stored as "the AOI actually queried", so it should mean what it says.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    if buffer_m <= 0:
        return polygon_from_bbox(min_lon, min_lat, max_lon, max_lat)

    mid_lat = (min_lat + max_lat) / 2.0
    d_lat = buffer_m / _M_PER_DEG_LAT
    m_per_deg_lon = _M_PER_DEG_LON_EQUATOR * math.cos(math.radians(mid_lat))
    d_lon = buffer_m / max(m_per_deg_lon, 1.0)
    return polygon_from_bbox(
        min_lon - d_lon, min_lat - d_lat, max_lon + d_lon, max_lat + d_lat
    )


def _parse_date(value: str, flag: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"{flag} must be YYYY-MM-DD, got {value!r}") from exc


class Command(BaseCommand):
    help = (
        "Retrieve satellite scenes over a Marsabit survey site, clip them to the "
        "AOI, and store validated COGs with PostGIS-verified footprints."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--site", required=True,
            help=f"Site code. One of: {', '.join(sorted(SITES_BY_CODE))}.",
        )
        parser.add_argument(
            "--dataset", required=True,
            help="SatelliteDataset code, e.g. 's2', 'l9'. See seed_datasets.",
        )
        parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
        parser.add_argument(
            "--end", default=None,
            help="End date, YYYY-MM-DD. Defaults to today (exclusive, as Earth "
                 "Engine treats it).",
        )
        parser.add_argument(
            "--max-cloud", type=float, default=None,
            help="Cloud ceiling in percent. IGNORED with a warning for datasets "
                 "with no cloud property — filtering on an absent property "
                 "returns an empty collection that reads as 'no scenes here'.",
        )
        parser.add_argument(
            "--limit", type=int, default=DEFAULT_LIMIT,
            help=f"Maximum scenes to download. Default {DEFAULT_LIMIT}.",
        )
        parser.add_argument(
            "--buffer-m", type=float, default=DEFAULT_BUFFER_M,
            help=f"Padding around the site bbox in metres. Default "
                 f"{DEFAULT_BUFFER_M:.0f}. The buffered polygon is what gets "
                 f"stored as the query AOI.",
        )
        parser.add_argument(
            "--org", default=None,
            help="Organization slug that owns the query. Optional when exactly "
                 "one organization exists.",
        )
        parser.add_argument(
            "--label", default="", help="Human handle for the query row.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Search and print matching scenes. Writes nothing, downloads "
                 "nothing, and creates no query row.",
        )
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Re-download and re-translate scenes whose COG is already on "
                 "disk. Off by default: the file is the expensive artefact.",
        )

    # ── entry point ──────────────────────────────────────────────────────

    def handle(self, *args, **options):
        site = self._resolve_site(options["site"])
        dataset = self._resolve_dataset(options["dataset"])
        start = _parse_date(options["start"], "--start")
        end = (
            _parse_date(options["end"], "--end")
            if options["end"] else timezone.localdate()
        )
        if end <= start:
            raise CommandError(f"--end ({end}) must be after --start ({start})")

        max_cloud = self._resolve_cloud(dataset, options["max_cloud"])
        aoi = buffered_aoi(site["bbox"], options["buffer_m"])

        self.stdout.write(
            f"{site['name']} · {dataset.code} · {start}..{end} · "
            f"buffer {options['buffer_m']:.0f} m · AOI "
            f"{tuple(round(v, 5) for v in aoi.extent)}"
        )

        if options["dry_run"]:
            return self._dry_run(dataset, aoi, start, end, max_cloud, options["limit"])

        org = self._resolve_org(options["org"])
        query = SatelliteQuery.objects.create(
            organization=org,
            dataset=dataset,
            mission=self._find_mission(org, site["code"]),
            geometry=aoi,
            label=options["label"] or f"{site['code']}-{dataset.code}-{start:%Y%m}",
            start_date=start,
            end_date=end,
            max_cloud_pct=max_cloud,
            status=SatelliteQuery.Status.RUNNING,
        )

        try:
            scenes = self._search(dataset, aoi, start, end, max_cloud, options["limit"])
        except gee_client.GEEError as exc:
            self._fail(query, f"Search failed: {exc}")
            raise CommandError(str(exc)) from exc

        if not scenes:
            query.status = SatelliteQuery.Status.EMPTY
            query.completed_at = timezone.now()
            query.save(update_fields=["status", "completed_at", "updated_at"])
            self.stdout.write(self.style.WARNING(
                "No scenes matched. That is a result, not a failure — widen the "
                "dates or raise --max-cloud."
            ))
            return

        stored, failures = self._retrieve(
            query=query, dataset=dataset, site=site, org=org, scenes=scenes,
            overwrite=options["overwrite"],
        )
        self._finalize(query, dataset, stored, failures)

    # ── resolution helpers ───────────────────────────────────────────────

    def _resolve_site(self, code: str) -> dict:
        try:
            return SITES_BY_CODE[code]
        except KeyError:
            raise CommandError(
                f"Unknown site {code!r}. Known: {', '.join(sorted(SITES_BY_CODE))}"
            ) from None

    def _resolve_dataset(self, code: str) -> SatelliteDataset:
        try:
            return SatelliteDataset.objects.get(code=code, is_active=True)
        except SatelliteDataset.DoesNotExist:
            known = list(
                SatelliteDataset.objects.filter(is_active=True)
                .order_by("code").values_list("code", flat=True)
            )
            raise CommandError(
                f"No active dataset with code {code!r}. Known: "
                f"{', '.join(known) or '(none — run seed_datasets)'}"
            ) from None

    def _resolve_org(self, slug: str | None) -> Organization:
        if slug:
            try:
                return Organization.objects.get(slug=slug)
            except Organization.DoesNotExist:
                raise CommandError(f"No organization with slug {slug!r}") from None

        orgs = list(Organization.objects.order_by("slug")[:2])
        if len(orgs) == 1:
            return orgs[0]
        available = ", ".join(
            Organization.objects.order_by("slug").values_list("slug", flat=True)
        )
        raise CommandError(
            "--org is required when more than one organization exists. "
            f"Available: {available or '(none — run seed_demo or seed_marsabit)'}"
        )

    def _resolve_cloud(self, dataset: SatelliteDataset, max_cloud):
        if max_cloud is None:
            return None
        if not dataset.cloud_property:
            self.stdout.write(self.style.WARNING(
                f"--max-cloud ignored: {dataset.code} has no cloud property "
                "(radar and reanalysis products have no cloud concept). "
                "Filtering on it would return an empty collection that looks "
                "exactly like 'no scenes available'."
            ))
            return None
        if not 0 <= max_cloud <= 100:
            raise CommandError(f"--max-cloud must be 0-100, got {max_cloud}")
        return max_cloud

    def _find_mission(self, org: Organization, site_code: str):
        """Link to the seeded mission for this site, if there is one.

        seed_marsabit stamps `metadata.site_code` on each mission, so the link
        survives renames of the mission itself.
        """
        return (
            Mission.objects.filter(organization=org, metadata__site_code=site_code)
            .order_by("id").first()
        )

    # ── search ───────────────────────────────────────────────────────────

    def _search(self, dataset, aoi, start, end, max_cloud, limit):
        return gee_client.search_scenes(
            collection_id=dataset.gee_collection_id,
            geometry=aoi,
            start=start,
            end=end,
            max_cloud=max_cloud,
            cloud_property=dataset.cloud_property,
            limit=limit,
        )

    def _dry_run(self, dataset, aoi, start, end, max_cloud, limit):
        try:
            scenes = self._search(dataset, aoi, start, end, max_cloud, limit)
        except gee_client.GEEError as exc:
            raise CommandError(str(exc)) from exc

        if not scenes:
            self.stdout.write(self.style.WARNING("No scenes matched."))
            return

        estimate = gee_client.estimate_download_bytes(
            geometry=aoi,
            scale_m=dataset.resolution_m,
            band_count=len(dataset.bands) or 1,
        )
        for scene in scenes:
            self.stdout.write(f"  {scene}")
        self.stdout.write(
            f"\n{len(scenes)} scene(s), ~{estimate / 1e6:.1f} MB each "
            f"({len(dataset.bands) or 'all'} band(s) at {dataset.resolution_m} m). "
            "Nothing written — drop --dry-run to retrieve."
        )

    # ── retrieval ────────────────────────────────────────────────────────

    def _retrieve(self, *, query, dataset, site, org, scenes, overwrite):
        stored: list[SatelliteImage] = []
        failures: list[str] = []

        for scene in scenes:
            try:
                image = self._retrieve_one(
                    query=query, dataset=dataset, site=site, org=org,
                    scene=scene, overwrite=overwrite,
                )
            except (gee_client.GEEError, cog.CogError, ValueError) as exc:
                failures.append(f"{scene.asset_id}: {exc}")
                self.stdout.write(self.style.ERROR(f"  FAILED {scene.asset_id}: {exc}"))
                continue
            stored.append(image)

        return stored, failures

    def _retrieve_one(self, *, query, dataset, site, org, scene, overwrite):
        # The AOI is part of the file's identity, not just its metadata — the
        # file is a CLIP. Without this, sites sharing a Sentinel-2 tile share
        # a filename and the second silently inherits the first's pixels.
        relative = cog.relative_cog_path(
            org_slug=org.slug,
            dataset_code=dataset.code,
            asset_id=scene.asset_id,
            aoi_key=site["code"] if site else f"query-{query.pk}",
        )
        destination = cog.absolute_cog_path(relative)

        if destination.exists() and not overwrite:
            self.stdout.write(f"  reusing {relative}")
            info = cog.inspect_cog(destination)
        else:
            payload = gee_client.download_clipped_geotiff(
                asset_id=scene.asset_id,
                geometry=query.geometry,
                bands=dataset.bands,
                scale_m=dataset.resolution_m,
            )
            info = cog.bytes_to_cog(
                payload,
                destination,
                overwrite=True,  # existence was decided above
                # Earth Engine returns the selected bands in order but unnamed.
                # Labelling them here is what stops `dataset.bands` ordering
                # from becoming an undocumented contract F10.4 depends on.
                band_names=dataset.bands,
                tags=self._provenance_tags(
                    dataset=dataset, site=site, org=org, scene=scene, query=query
                ),
            )
            self.stdout.write(
                f"  wrote {relative} ({info.width}x{info.height}px, "
                f"{info.band_count} band(s), {info.size_bytes / 1e3:.0f} kB)"
            )

        footprint = polygon_from_bbox(*info.bounds_4326)

        with transaction.atomic():
            image, _ = SatelliteImage.objects.update_or_create(
                query=query,
                gee_asset_id=scene.asset_id,
                defaults={
                    "dataset": dataset,
                    "acquisition_date": scene.acquisition_date,
                    "cloud_cover_pct": scene.cloud_cover_pct,
                    "geometry": footprint,
                    "cog_path": relative,
                    "size_bytes": info.size_bytes,
                    "downloaded_at": timezone.now(),
                    "bands": info.band_names,
                    "properties": scene.properties,
                },
            )
            self._assert_intersects(image, query)

        return image

    def _assert_intersects(self, image: SatelliteImage, query: SatelliteQuery) -> None:
        """Prove in the database that the stored footprint touches the AOI.

        Deliberately a PostGIS query rather than a GEOS call: this is the same
        index-backed predicate F10.4's correlation join will use, so if it does
        not hold here it will not hold there either.
        """
        intersects = SatelliteImage.objects.filter(
            pk=image.pk, geometry__intersects=query.geometry
        ).exists()
        if not intersects:
            raise ValueError(
                "Stored footprint does not intersect the queried AOI in PostGIS. "
                f"Footprint {tuple(round(v, 5) for v in image.geometry.extent)} vs "
                f"AOI {tuple(round(v, 5) for v in query.geometry.extent)}."
            )

    def _provenance_tags(self, *, dataset, site, org, scene, query) -> dict[str, str]:
        """Metadata written inside the GeoTIFF.

        Provenance that travels with the file survives a database restore, a
        copy onto someone's laptop, and a QGIS session. A row in a table does
        not.
        """
        return {
            "RANGER_SOURCE": "Google Earth Engine",
            "RANGER_COLLECTION": dataset.gee_collection_id,
            "RANGER_DATASET": dataset.code,
            "RANGER_ASSET_ID": scene.asset_id,
            "RANGER_SITE": f"{site['code']} — {site['name']}",
            "RANGER_AOI_BBOX": ",".join(f"{v:.6f}" for v in query.geometry.extent),
            "RANGER_ACQUIRED": scene.acquisition_date.isoformat(),
            "RANGER_RETRIEVED": timezone.now().isoformat(),
            "RANGER_ORG": org.slug,
            "RANGER_VALUES": (
                "raw sensor DN — no scale factor or offset applied "
                "(S2 SR is x10000; Landsat C2 L2 carries its own scale/offset)"
            ),
        }

    # ── completion ───────────────────────────────────────────────────────

    def _finalize(self, query, dataset, stored, failures):
        query.scene_count = len(stored)
        query.completed_at = timezone.now()
        query.error_message = "\n".join(failures)

        if stored:
            query.status = SatelliteQuery.Status.COMPLETE
            if not dataset.is_verified:
                dataset.is_verified = True
                dataset.save(update_fields=["is_verified", "updated_at"])
                self.stdout.write(self.style.SUCCESS(
                    f"{dataset.code} marked verified — a real scene is on disk."
                ))
        else:
            query.status = SatelliteQuery.Status.FAILED

        query.save(update_fields=[
            "status", "scene_count", "completed_at", "error_message", "updated_at",
        ])

        media = getattr(settings, "MEDIA_ROOT", "")
        style = self.style.SUCCESS if stored else self.style.ERROR
        self.stdout.write(style(
            f"\nquery {query.pk}: {query.status} — {len(stored)} stored, "
            f"{len(failures)} failed. Files under {media}/{cog.SATELLITE_SUBDIR}/"
        ))
        if not stored:
            raise CommandError("No scenes were retrieved.")

    def _fail(self, query, message: str) -> None:
        query.status = SatelliteQuery.Status.FAILED
        query.error_message = message
        query.completed_at = timezone.now()
        query.save(update_fields=[
            "status", "error_message", "completed_at", "updated_at",
        ])
# ─── RANGER V3 END: fetch_scenes ───