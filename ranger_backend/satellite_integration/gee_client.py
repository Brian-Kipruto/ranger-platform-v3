# ─── RANGER V3 START: gee client ───
"""
Earth Engine service wrapper (F10.2 CP4).

Design rules, each of which cost something to learn:

1. INITIALIZATION IS LAZY. Importing this module must never require
   credentials. `manage.py check`, `migrate`, and the entire test suite import
   the app; if import triggered ee.Initialize(), every one of them would need
   a service-account key. Initialization happens on first real call.

2. EXCEPTIONS ARE TYPED. Earth Engine reports configuration errors, auth
   failures, and quota exhaustion as the same `ee.EEException` with different
   message text. Callers cannot branch on prose, so this module translates
   once, here. The 403 during CP0 setup — key valid, roles missing — is
   exactly the case that needs to be distinguishable from "wrong key".

3. NO CREDENTIALS ARE EVER LOGGED. Not the key path's contents, not on error.

4. ONE getInfo() PER SEARCH. Every getInfo() is a synchronous round trip that
   spends EECU quota. Fetching the collection once and reading features
   locally costs one call; looping images and calling getInfo() per scene
   costs n. On the Community Tier that difference is the difference between
   comfortable and rate-limited.

Geometry crosses the boundary as GeoJSON: GEOS -> ee on the way in, ee ->
GEOS on the way out, always SRID 4326 (ADR-0011), so nothing downstream has
to think about projections.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Polygon

logger = logging.getLogger(__name__)

# ── Exceptions ───────────────────────────────────────────────────────────


class GEEError(Exception):
    """Base for every Earth Engine failure this module raises."""


class GEEConfigurationError(GEEError):
    """Settings missing or key file unreadable. Fix .env, not the code."""


class GEEAuthenticationError(GEEError):
    """Credentials rejected, or the service account lacks project roles.

    The common case is roles, not the key: a valid key with no
    `serviceusage.serviceUsageConsumer` role 403s on every call while looking
    exactly like a credentials problem. See troubleshooting 018.
    """


class GEEQuotaError(GEEError):
    """Rate limit or EECU quota exhausted. Retry later; do not hammer."""


class GEECollectionError(GEEError):
    """The collection ID does not exist or is not accessible."""


# ── Scene metadata ───────────────────────────────────────────────────────


@dataclass
class SceneMetadata:
    """One scene, normalized across collections.

    Deliberately a plain dataclass rather than a model instance: searching is
    not persisting, and CP5 decides what is worth keeping.
    """

    asset_id: str
    acquisition_date: datetime
    footprint: Polygon
    cloud_cover_pct: float | None = None
    bands: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        cloud = "n/a" if self.cloud_cover_pct is None else f"{self.cloud_cover_pct:.1f}%"
        return f"{self.asset_id} @ {self.acquisition_date:%Y-%m-%d} (cloud {cloud})"


# ── Client ───────────────────────────────────────────────────────────────

_initialized = False


def is_configured() -> bool:
    """True if all three settings are present. Does NOT contact Google.

    Tests use this to skip integration cases without importing ee or making
    a network call.
    """
    return all([
        getattr(settings, "GEE_PROJECT_ID", ""),
        getattr(settings, "GEE_SERVICE_ACCOUNT_EMAIL", ""),
        getattr(settings, "GEE_KEY_PATH", ""),
    ])


def _translate(exc: Exception) -> GEEError:
    """Map an ee.EEException onto a typed error.

    Message sniffing is unpleasant, but Earth Engine does not expose error
    codes through the Python client, and the alternative is making every
    caller parse prose.
    """
    text = str(exc)
    lowered = text.lower()

    if "not signed up" in lowered or "not registered" in lowered:
        return GEEConfigurationError(
            "The Cloud project is not registered for Earth Engine. "
            "Check GEE_PROJECT_ID matches the registered project."
        )
    if any(s in lowered for s in (
        "permission", "403", "caller does not have", "serviceusage",
        "unauthenticated", "invalid_grant", "credential",
    )):
        return GEEAuthenticationError(
            "Earth Engine rejected the service account. Most often this is "
            "missing IAM roles rather than a bad key — the account needs both "
            "Service Usage Consumer and Earth Engine Resource Writer. "
            f"Underlying error: {text}"
        )
    if any(s in lowered for s in ("quota", "rate limit", "429", "too many requests")):
        return GEEQuotaError(f"Earth Engine quota or rate limit hit: {text}")
    if any(s in lowered for s in ("not found", "does not exist", "no such")):
        return GEECollectionError(text)
    return GEEError(text)


def initialize(force: bool = False) -> None:
    """Authenticate with Earth Engine. Idempotent; safe to call repeatedly."""
    global _initialized
    if _initialized and not force:
        return

    if not is_configured():
        missing = [
            name for name in
            ("GEE_PROJECT_ID", "GEE_SERVICE_ACCOUNT_EMAIL", "GEE_KEY_PATH")
            if not getattr(settings, name, "")
        ]
        raise GEEConfigurationError(
            f"Earth Engine is not configured. Missing: {', '.join(missing)}. "
            "Set these in .env (see .env.example)."
        )

    import ee  # imported lazily so the package is optional at import time

    key_path = settings.GEE_KEY_PATH
    try:
        credentials = ee.ServiceAccountCredentials(
            settings.GEE_SERVICE_ACCOUNT_EMAIL, key_path
        )
        ee.Initialize(credentials, project=settings.GEE_PROJECT_ID)
    except FileNotFoundError as exc:
        # Path only — never the file's contents.
        raise GEEConfigurationError(
            f"Service account key not found at {key_path}"
        ) from exc
    except Exception as exc:
        raise _translate(exc) from exc

    _initialized = True
    logger.info("Earth Engine initialized for project %s", settings.GEE_PROJECT_ID)


def _to_ee_geometry(geom: GEOSGeometry):
    import ee

    if geom.srid not in (None, 4326):
        geom = geom.transform(4326, clone=True)
    return ee.Geometry(json.loads(geom.geojson))


def _footprint_to_polygon(footprint: dict | None, fallback: Polygon) -> Polygon:
    """ee footprints come back as GeoJSON; some products omit them."""
    if not footprint:
        return fallback
    try:
        # GEE emits Landsat footprints as LinearRing, which is NOT a valid
        # GeoJSON geometry type — GEOSGeometry rejects it. Convert to Polygon.
        if footprint.get("type") == "LinearRing" and footprint.get("coordinates"):
            ring = [tuple(c) for c in footprint["coordinates"]]
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            return Polygon(ring, srid=4326)

        geom = GEOSGeometry(json.dumps(footprint), srid=4326)
        if geom.geom_type == "Polygon":
            return geom
        # Multi-part or ring geometries: the convex hull is a fair extent and
        # keeps the model's PolygonField honest.
        hull = geom.convex_hull
        return hull if hull.geom_type == "Polygon" else fallback
    except Exception:  # malformed footprint is not worth failing a search over
        logger.warning("Unparseable scene footprint; falling back to AOI")
        return fallback


def search_scenes(
    collection_id: str,
    geometry: GEOSGeometry,
    start: date,
    end: date,
    max_cloud: float | None = None,
    cloud_property: str = "",
    limit: int = 50,
) -> list[SceneMetadata]:
    """Find scenes intersecting `geometry` between `start` and `end`.

    Args:
        collection_id: e.g. "COPERNICUS/S2_SR_HARMONIZED".
        geometry: AOI, any GEOS geometry in 4326.
        start, end: inclusive-exclusive date bounds, as Earth Engine treats them.
        max_cloud: cloud ceiling in percent. Ignored unless `cloud_property`
            is also given — radar and reanalysis products have no cloud
            metadata at all, and filtering on an absent property returns an
            empty collection rather than an error, which looks exactly like
            "no scenes available".
        cloud_property: the collection's cloud field. Varies by product
            (Sentinel-2: CLOUDY_PIXEL_PERCENTAGE, Landsat C2: CLOUD_COVER),
            which is why it lives on SatelliteDataset rather than in a
            hardcoded map here.
        limit: scene cap. Guards both memory and EECU spend.

    Returns:
        Scenes newest first. An empty list means no matches — not an error.
    """
    initialize()
    import ee

    aoi = _to_ee_geometry(geometry)
    fallback = geometry if isinstance(geometry, Polygon) else geometry.envelope

    try:
        collection = (
            ee.ImageCollection(collection_id)
            .filterBounds(aoi)
            .filterDate(start.isoformat(), end.isoformat())
        )
        if max_cloud is not None and cloud_property:
            collection = collection.filter(ee.Filter.lte(cloud_property, max_cloud))

        # THE single getInfo(). Everything below reads local data.
        info = collection.sort("system:time_start", False).limit(limit).getInfo()
    except Exception as exc:
        raise _translate(exc) from exc

    scenes: list[SceneMetadata] = []
    for feature in (info or {}).get("features", []):
        props = feature.get("properties", {}) or {}

        millis = props.get("system:time_start")
        if millis is None:
            logger.warning("Scene %s has no timestamp; skipped", feature.get("id"))
            continue
        acquired = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)

        cloud = props.get(cloud_property) if cloud_property else None

        scenes.append(SceneMetadata(
            asset_id=feature.get("id", ""),
            acquisition_date=acquired,
            footprint=_footprint_to_polygon(props.get("system:footprint"), fallback),
            cloud_cover_pct=float(cloud) if cloud is not None else None,
            bands=[b.get("id") for b in feature.get("bands", []) if b.get("id")],
            # Keep the raw properties verbatim: provenance beats tidiness, and
            # F10.4 will want fields nobody has thought of yet.
            properties={k: v for k, v in props.items() if not k.startswith("system:")},
        ))

    return scenes


def collection_exists(collection_id: str) -> bool:
    """Cheap existence check for a collection ID.

    The catalog's IDs are hand-entered from Google's documentation, so a typo
    is entirely possible and would otherwise surface as an empty search
    result — indistinguishable from "no scenes here".
    """
    initialize()
    import ee

    try:
        ee.ImageCollection(collection_id).limit(1).size().getInfo()
        return True
    except Exception as exc:
        translated = _translate(exc)
        if isinstance(translated, GEECollectionError):
            return False
        raise translated from exc


# ── Download (CP5) ───────────────────────────────────────────────────────

# getDownloadURL refuses requests above roughly 32 MB with an opaque server
# error. We check first, so the failure names the actual problem — too much
# area, too fine a scale, or too many bands — instead of a 400 from Google.
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024

# Bytes per pixel per band used when estimating. Sentinel-2 SR comes back as
# int16 (2 bytes), but Earth Engine promotes mixed-type band selections to
# float32, so estimate at 4 and be wrong in the safe direction.
_ESTIMATE_BYTES_PER_PIXEL = 4

# Metres per degree of latitude, and per degree of longitude at the equator.
# Both are approximations on a sphere; at the sizes we clip to (a couple of
# kilometres) the error is well under one pixel, and this is a guard rail, not
# a geodesy library.
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON_EQUATOR = 111_320.0

_DOWNLOAD_ATTEMPTS = 3
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_CONNECT_TIMEOUT_S = 30
_READ_TIMEOUT_S = 300


class GEEDownloadError(GEEError):
    """The download URL was issued but fetching the bytes failed."""


class GEEPayloadTooLargeError(GEEError):
    """The requested clip exceeds what getDownloadURL will serve.

    Shrink the AOI, coarsen the scale, or select fewer bands. This is a
    request-shaping problem, never a transient one, so callers must not retry.
    """


def estimate_download_bytes(
    *,
    geometry: GEOSGeometry,
    scale_m: float,
    band_count: int,
    bytes_per_pixel: int = _ESTIMATE_BYTES_PER_PIXEL,
) -> int:
    """Approximate the size of a clipped GeoTIFF before requesting it."""
    import math

    west, south, east, north = geometry.extent
    mid_lat_rad = math.radians((south + north) / 2.0)
    # cos() collapses at the poles; nothing we clip is near them, but a zero
    # here would divide the estimate into infinity.
    m_per_deg_lon = max(_M_PER_DEG_LON_EQUATOR * math.cos(mid_lat_rad), 1.0)

    width_px = math.ceil((east - west) * m_per_deg_lon / scale_m)
    height_px = math.ceil((north - south) * _M_PER_DEG_LAT / scale_m)
    return max(width_px, 1) * max(height_px, 1) * max(band_count, 1) * bytes_per_pixel


def _fetch_bytes(url: str, max_bytes: int) -> bytes:
    """GET `url`, streaming, with bounded retries and a hard size ceiling."""
    import time

    import requests

    last_error: Exception | None = None

    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            with requests.get(
                url, stream=True, timeout=(_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)
            ) as response:
                if response.status_code in _RETRY_STATUS:
                    last_error = GEEDownloadError(
                        f"HTTP {response.status_code} from the download endpoint"
                    )
                    raise last_error
                response.raise_for_status()

                # Never trust Content-Length alone — cap while reading, so a
                # mis-declared or absent header cannot fill the disk.
                buffer = bytearray()
                for chunk in response.iter_content(chunk_size=1 << 20):
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise GEEPayloadTooLargeError(
                            f"Download exceeded {max_bytes} bytes mid-stream; "
                            "aborted. Reduce the AOI, the scale, or the bands."
                        )
                return bytes(buffer)

        except GEEPayloadTooLargeError:
            raise  # never retry a request that is simply too big
        except Exception as exc:  # requests errors and the retry raise above
            last_error = exc
            if attempt == _DOWNLOAD_ATTEMPTS:
                break
            backoff = 2 ** attempt
            logger.warning(
                "Download attempt %d/%d failed (%s); retrying in %ds",
                attempt, _DOWNLOAD_ATTEMPTS, exc, backoff,
            )
            time.sleep(backoff)

    raise GEEDownloadError(
        f"Download failed after {_DOWNLOAD_ATTEMPTS} attempts: {last_error}"
    ) from last_error


def download_clipped_geotiff(
    *,
    asset_id: str,
    geometry: GEOSGeometry,
    bands: list[str] | None = None,
    scale_m: float = 10.0,
    crs: str = "EPSG:4326",
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> bytes:
    """Download one scene, clipped to `geometry`, as GeoTIFF bytes.

    Args:
        asset_id: full Earth Engine image ID, e.g.
            "COPERNICUS/S2_SR_HARMONIZED/20260118T073211_...". This is the
            durable identifier; tile URLs are not.
        geometry: clip region, WGS84. CLIPPING IS NOT OPTIONAL — a full
            Sentinel-2 tile is ~1 GB and the sites are 100-300 m across, so an
            unclipped request would spend Community Tier quota on a million
            times more pixels than anybody looks at.
        bands: bands to select. None means every band in the image, which for
            Sentinel-2 SR is 20-odd at mixed native resolutions. Pass the
            catalog's `dataset.bands`.
        scale_m: output pixel size in metres. Earth Engine resamples to this
            regardless of `crs`.
        crs: output projection. EPSG:4326 by default so the raster shares a CRS
            with SensorLog geometry, the AOI polygon, MapLibre, and deck.gl —
            no reprojection anywhere in the stack (ADR-0012).
        max_bytes: ceiling, checked before the request and again while reading.

    Returns:
        Raw GeoTIFF bytes. The caller decides whether they become a COG.

    Raises:
        GEEPayloadTooLargeError: the clip is too big to serve. Not transient.
        GEEDownloadError: the bytes could not be fetched.
        GEEAuthenticationError, GEEQuotaError, GEECollectionError: as elsewhere.
    """
    initialize()
    import ee

    band_list = list(bands) if bands else []
    estimated = estimate_download_bytes(
        geometry=geometry, scale_m=scale_m, band_count=len(band_list) or 1
    )
    if estimated > max_bytes:
        raise GEEPayloadTooLargeError(
            f"Estimated {estimated / 1e6:.1f} MB exceeds the {max_bytes / 1e6:.0f} MB "
            f"download limit ({len(band_list) or 'all'} band(s) at {scale_m} m over "
            f"{geometry.extent}). Reduce --buffer-m, raise the scale, or select "
            "fewer bands."
        )

    region = _to_ee_geometry(geometry)
    try:
        image = ee.Image(asset_id)
        if band_list:
            image = image.select(band_list)
        url = image.getDownloadURL({
            "region": region,
            "scale": scale_m,
            "crs": crs,
            "format": "GEO_TIFF",
            # False, or Earth Engine hands back a ZIP of one file per band.
            "filePerBand": False,
        })
    except Exception as exc:
        raise _translate(exc) from exc

    logger.info(
        "Downloading %s (%d band(s), %s m, est %.1f MB)",
        asset_id, len(band_list) or 0, scale_m, estimated / 1e6,
    )
    return _fetch_bytes(url, max_bytes)
# ─── RANGER V3 END: gee client ───