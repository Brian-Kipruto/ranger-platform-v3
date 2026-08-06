# ─── RANGER V3 START: cog pipeline ───
"""
Raster I/O: GeoTIFF bytes in, validated Cloud-Optimized GeoTIFF on disk out.

Deliberately isolated from `gee_client`
---------------------------------------
`import rasterio` loads a bundled GDAL (~30 MB of shared objects). `check_gee`,
`seed_datasets`, and every test module in this app import `gee_client`; none of
them need GDAL. Keeping raster I/O behind its own module means the cheap paths
stay cheap, and it means the COG pipeline is testable with a synthetic raster
and no Earth Engine credentials at all.

Two rules this module enforces so callers cannot get them wrong:

1. WRITES ARE ATOMIC. Translation goes to `<dest>.partial` and is renamed onto
   `dest` only after validation passes. A crash, a kill, or a full disk
   therefore leaves no half-written file at a path a SatelliteImage row points
   at. `cog_path` on a row is a promise that the file is complete and valid.

2. FOOTPRINTS COME FROM THE FILE, NOT THE API. `inspect_cog` reads bounds off
   the raster and reprojects them to 4326. The scene footprint Earth Engine
   reports covers the whole Sentinel-2 tile; what we downloaded is a clip a
   thousand times smaller. Storing the API's footprint would over-claim
   coverage by three orders of magnitude, and every spatial query downstream
   would inherit the lie.
"""
from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# TIFF magic: little-endian ("II*\0") or big-endian ("MM\0*"). Earth Engine
# returns errors as HTML or JSON with a 200 status, so the only reliable way to
# tell a raster from an error page is to look at the first four bytes.
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


class CogError(Exception):
    """Raster conversion, validation, or inspection failed."""


@dataclass(frozen=True)
class CogInfo:
    """What a finished COG actually contains. Read from the file, not assumed."""

    path: Path
    size_bytes: int
    width: int
    height: int
    band_count: int
    band_names: list[str]
    crs: str
    dtype: str
    # (west, south, east, north) in EPSG:4326, whatever the raster's own CRS is.
    bounds_4326: tuple[float, float, float, float]

    @property
    def pixel_count(self) -> int:
        return self.width * self.height


def looks_like_tiff(data: bytes) -> bool:
    """True if `data` starts with a TIFF magic number."""
    return data.startswith(_TIFF_MAGIC)


def _bounds_4326(dataset) -> tuple[float, float, float, float]:
    from rasterio.warp import transform_bounds

    bounds = dataset.bounds
    if dataset.crs is None:
        raise CogError("Raster has no CRS; refusing to guess a footprint.")
    if dataset.crs.to_epsg() == 4326:
        return (bounds.left, bounds.bottom, bounds.right, bounds.top)
    return tuple(transform_bounds(dataset.crs, "EPSG:4326", *bounds, densify_pts=21))


def inspect_cog(path: str | os.PathLike) -> CogInfo:
    """Open a raster and report what is actually in it."""
    import rasterio

    path = Path(path)
    try:
        with rasterio.open(path) as src:
            names = [
                desc or f"band_{i}"
                for i, desc in enumerate(src.descriptions, start=1)
            ]
            return CogInfo(
                path=path,
                size_bytes=path.stat().st_size,
                width=src.width,
                height=src.height,
                band_count=src.count,
                band_names=names,
                crs=str(src.crs),
                dtype=src.dtypes[0] if src.dtypes else "",
                bounds_4326=_bounds_4326(src),
            )
    except CogError:
        raise
    except Exception as exc:
        raise CogError(f"Could not read raster at {path}: {exc}") from exc


def validate_cog(path: str | os.PathLike) -> None:
    """Raise CogError unless `path` is a valid COG. Warnings are logged only."""
    from rio_cogeo.cogeo import cog_validate

    is_valid, errors, warnings = cog_validate(str(path), quiet=True)
    for warning in warnings:
        logger.warning("COG warning for %s: %s", path, warning)
    if not is_valid:
        raise CogError(f"{path} is not a valid COG: {'; '.join(errors) or 'unknown'}")


class _PhotometricNoiseFilter(logging.Filter):
    """Drops ONE known-benign libtiff warning, and nothing else.

    Every Earth Engine multiband GeoTIFF declares PHOTOMETRIC=RGB with more
    samples than colour channels, so GDAL emits this twice per scene while
    reading the download. It says nothing about our output — `_dst_profile`
    declares minisblack explicitly, and `validate_cog` runs outside this
    filter, so a genuinely malformed COG still fails loudly.

    A message filter rather than a log level, deliberately: raising the level
    on rasterio._env would hide real raster warnings alongside this one, which
    is the trade nobody notices making until it costs them a day.
    """

    _NEEDLE = "Photometric type-related color channels"

    def filter(self, record: logging.LogRecord) -> bool:
        return self._NEEDLE not in record.getMessage()


@contextlib.contextmanager
def _without_photometric_noise():
    log = logging.getLogger("rasterio._env")
    noise_filter = _PhotometricNoiseFilter()
    log.addFilter(noise_filter)
    try:
        yield
    finally:
        log.removeFilter(noise_filter)


def _label_bands(path: Path, band_names) -> None:
    """Write band descriptions onto a plain GeoTIFF before translation.

    Earth Engine returns bands in the order they were selected but does NOT
    name them, so a downloaded scene arrives as band_1..band_n. That makes
    `SatelliteDataset.bands` ordering silently load-bearing: F10.4 selecting
    "the NDVI bands" would be indexing into an undocumented convention.

    Names are only written when the count matches exactly. A mislabelled band
    is far worse than an unlabelled one — it would be wrong in a way that
    reads as authoritative.
    """
    import rasterio

    if not band_names:
        return
    with rasterio.open(path, "r+") as dst:
        if len(band_names) != dst.count:
            logger.warning(
                "Not labelling bands: %d name(s) for %d band(s) in %s. "
                "The catalog's band list disagrees with what was downloaded.",
                len(band_names), dst.count, path,
            )
            return
        dst.descriptions = tuple(band_names)


def _dst_profile(profile: str) -> dict:
    """Creation options for the output, reconciled with the COG driver.

    Two mismatches that produce warnings on every single scene:

    * rio-cogeo's profiles target the GTiff driver and set INTERLEAVE, which
      GDAL's COG driver rejects outright. Harmless, but it warns each time.
    * Earth Engine emits multiband GeoTIFFs declaring PHOTOMETRIC=RGB with
      seven samples and no ExtraSamples, so GDAL complains on every read — and
      without an explicit value the mismatch is copied onto our output.

    Neither is fatal. Both are noise, and noise on a happy path is how you
    learn to scroll past the warning that actually matters.
    """
    from rio_cogeo.profiles import cog_profiles

    dst = {k: v for k, v in cog_profiles.get(profile).items() if k != "interleave"}
    # Multispectral bands are measurements, not colour channels.
    dst["photometric"] = "minisblack"
    return dst


def to_cog(
    source: str | os.PathLike,
    dest: str | os.PathLike,
    *,
    tags: dict[str, str] | None = None,
    overwrite: bool = False,
    profile: str = "deflate",
) -> CogInfo:
    """Translate `source` into a validated COG at `dest`.

    Args:
        source: any raster rasterio can open.
        dest: final path. Parent directories are created.
        tags: GeoTIFF metadata written into the file itself. Provenance that
            travels with the raster survives a database restore, a file copied
            to someone's laptop, and a QGIS session — which is more than can be
            said for a row in a table.
        overwrite: replace an existing `dest`. Default False: a COG already on
            disk is the expensive artefact, and silently rewriting it is how
            you burn quota re-downloading what you already had.
        profile: rio-cogeo profile name. DEFLATE is lossless, which is the only
            acceptable answer for data anyone might later measure.

    Returns:
        CogInfo read back from the finished file.
    """
    from rio_cogeo.cogeo import cog_translate

    source, dest = Path(source), Path(dest)
    if dest.exists() and not overwrite:
        raise CogError(f"{dest} already exists (pass overwrite=True to replace)")

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Same directory as dest, so the rename below is atomic (os.replace across
    # filesystems is not).
    partial = dest.with_name(dest.name + ".partial")

    try:
        with _without_photometric_noise():
            cog_translate(
                str(source),
                str(partial),
                _dst_profile(profile),
                in_memory=False,
                quiet=True,
                forward_band_tags=True,
                additional_cog_metadata=dict(tags or {}),
                use_cog_driver=True,
            )
        validate_cog(partial)
        info = inspect_cog(partial)
        os.replace(partial, dest)
    except CogError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise CogError(f"COG translation failed for {source}: {exc}") from exc

    logger.info("Wrote COG %s (%d bytes)", dest, info.size_bytes)
    # Re-read at the final path so CogInfo.path is the path callers will store.
    return inspect_cog(dest)


def bytes_to_cog(
    data: bytes,
    dest: str | os.PathLike,
    *,
    tags: dict[str, str] | None = None,
    band_names: list[str] | None = None,
    overwrite: bool = False,
) -> CogInfo:
    """Write downloaded GeoTIFF bytes straight to a validated COG.

    `band_names` are stamped onto the temporary source before translation —
    this function owns that file, so writing to it is safe, whereas reopening
    a finished COG to edit metadata risks its layout.
    """
    import tempfile

    if not looks_like_tiff(data):
        preview = data[:200].decode("utf-8", errors="replace")
        raise CogError(
            "Downloaded payload is not a GeoTIFF. Earth Engine returns errors "
            f"with a 200 status, so this is probably one. First bytes: {preview!r}"
        )

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        with _without_photometric_noise():
            _label_bands(tmp_path, band_names)
        return to_cog(tmp_path, dest, tags=tags, overwrite=overwrite)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Storage layout ───────────────────────────────────────────────────────
# SatelliteImage.cog_path is documented as relative to MEDIA_ROOT/satellite/.
# Both halves of that contract live here so the writer (fetch_scenes) and the
# reader (the CP6 API, and F10.3's tile serving) cannot drift apart.

SATELLITE_SUBDIR = "satellite"

# Note the absence of ".". Real Earth Engine asset IDs do not contain dots, we
# append the extension ourselves, and allowing them would let ".." survive into
# a filename. Nothing is lost and one whole class of path bug goes away.
_SAFE_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def sanitize_asset_id(asset_id: str) -> str:
    """Flatten an Earth Engine asset ID into one safe filename component.

    Asset IDs contain slashes ("COPERNICUS/S2_SR_HARMONIZED/20260118T073211")
    and would otherwise silently create a directory tree — and a path
    traversal, if an ID ever contained "..".
    """
    flattened = asset_id.replace("/", "_")
    cleaned = "".join(c if c in _SAFE_CHARS else "-" for c in flattened).strip("-_")
    if not cleaned:
        raise CogError(f"Asset ID {asset_id!r} sanitizes to an empty filename")
    return cleaned


def relative_cog_path(*, org_slug: str, dataset_code: str, asset_id: str) -> str:
    """The value to store in SatelliteImage.cog_path."""
    return (
        f"{sanitize_asset_id(org_slug)}/{sanitize_asset_id(dataset_code)}/"
        f"{sanitize_asset_id(asset_id)}.tif"
    )


def absolute_cog_path(relative: str) -> Path:
    """Resolve a stored cog_path against MEDIA_ROOT/satellite/."""
    from django.conf import settings

    root = (Path(settings.MEDIA_ROOT) / SATELLITE_SUBDIR).resolve()
    resolved = (root / relative).resolve()
    # Defence in depth: relative_cog_path already sanitizes, but this path is
    # the one that will eventually be handed to a file-serving view.
    if not str(resolved).startswith(str(root) + os.sep):
        raise CogError(f"Refusing to resolve {relative!r} outside {root}")
    return resolved
# ─── RANGER V3 END: cog pipeline ───