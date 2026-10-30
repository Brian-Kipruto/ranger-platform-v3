# ─── RANGER V3 START: 16-report-branding ───
"""
Tenant branding for the compliance report (F16, 7b step 4).

The client's brand leads: they hand this report to a regulator. R.A.N.G.E.R.
and ByteAnza appear only as the producer line and the footer.

Two inputs come from the database and are treated as untrusted:

* Organization.theme_color is a free CharField that ends up inside CSS.
  Anything that is not exactly #rrggbb is replaced with the default, or a
  value like `red;}body{display:none` would restyle the report.
* Organization.logo is any uploaded file. It is opened with Pillow, verified,
  downscaled and re-encoded as PNG. A missing, corrupt or non-image file
  falls back to the org name; branding never sinks a report.

The accent is used for rules and borders only, never for text, so a pale
tenant colour cannot make anything unreadable, and never for the provenance
band, whose amber/red must not change with a tenant's theme.
"""
from __future__ import annotations

import base64
import io
import logging
import re

from PIL import Image

log = logging.getLogger(__name__)

DEFAULT_ACCENT = "#0ea5e9"   # Organization.theme_color's model default
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_MAX_PX = (800, 300)     # enough for ~18 mm tall at print resolution
PRODUCER = "Produced with R.A.N.G.E.R. · ByteAnza"


def accent(org) -> str:
    value = (getattr(org, "theme_color", "") or "").strip()
    return value.lower() if HEX.match(value) else DEFAULT_ACCENT


def logo(org) -> dict | None:
    """{'src': data URI, 'width': px, 'height': px} or None."""
    field = getattr(org, "logo", None)
    if not field:
        return None
    try:
        with field.open("rb") as f:
            raw = f.read()
        # verify() is load-bearing. WeasyPrint sets Pillow's process-global
        # ImageFile.LOAD_TRUNCATED_IMAGES = True on import, after which a
        # truncated upload DECODES SILENTLY into a half-blank logo. verify()
        # still raises on truncation with that flag set; decoding does not.
        Image.open(io.BytesIO(raw)).verify()
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img.thumbnail(LOGO_MAX_PX)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
    except Exception as exc:  # missing file, not an image, truncated...
        log.warning("report logo skipped for org %s: %s", getattr(org, "pk", "?"), exc)
        return None
    return {
        "src": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
        "width": img.width,
        "height": img.height,
    }


def branding(org) -> dict:
    lg = logo(org)
    return {"accent": accent(org), "logo": lg, "producer": PRODUCER}
# ─── RANGER V3 END: 16-report-branding ───
