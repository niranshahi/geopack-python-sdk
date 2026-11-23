"""Lane B — the built-in, user-customizable map viewer (slice 033).

The render engine's product is a **live map URL**, not an image: this module
turns a merged template + the ``/manifest.json`` layer contract into one HTML
page that an **OpenLayers** runtime draws in the browser. OpenLayers is the one
lightweight library that renders every layer family the portal serves natively
(GeoJSON, MVT vector tiles, WMS/WMTS images, WFS vector data, XYZ raster), so no
plugin layer is needed. The viewer is isolated here, so the library is swappable
without touching the service.

**Templates (N6) — the page is a resource file, not a Python string.** The
shipped default lives in ``templates/default/`` as ``viewer.html`` +
``template.json`` and is read from disk, so the entire page is editable without
touching code. Precedence, lowest → highest:

1. shipped default — ``templates/default/viewer.html`` + ``template.json`` (read-only).
2. user config — ``viewer.html`` / ``template.json`` / ``viewer.css`` under
   ``GEOPACK_MCP_MAP_TEMPLATES`` or ``~/.geopack/mcp/maps/``.
3. per-call — the ``template`` / ``basemap`` / ``title`` arguments of ``show_map``.

``template.json`` deep-merges across the tiers; a type error falls back to the
default **for that key** while recording a ``templateWarnings[]`` entry — never a
crash, never a silent wrong map. A Tier-2 ``viewer.html`` replaces the shipped
page wholesale, but only when it keeps the required ``__…__`` placeholders
(checked by :func:`load_viewer_html`); otherwise the shipped page is used and a
warning recorded, so a broken custom page can never ship.

The rendered page fixes the OSM "access blocked" case in-browser: the shell is
served with ``Referrer-Policy: strict-origin-when-cross-origin`` (origin-only, so
the ``?t=`` token never leaks), and each XYZ tile ``<img>`` additionally sets a
per-element ``referrerPolicy`` of ``strict-origin-when-cross-origin`` — the
element policy overrides the document policy, so OSM receives the origin as
``Referer`` (never the path/query) and serves real tiles. Mirrors the frontend
``OsmWebTileLayer``.
"""

from __future__ import annotations

import copy
import html
import json
import os
from typing import Any, Dict, List, Optional, Tuple

#: Where the shipped default template lives inside the package.
DEFAULT_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates", "default")

#: OpenLayers build served to the browser. Pinned; a vendored copy overrides it.
DEFAULT_OL_VERSION = "10.6.1"
#: The legacy OpenLayers build does NOT embed geotiff.js; its GeoTIFF source reads
#: the global ``GeoTIFF`` (from the geotiff UMD bundle), so the page must load it
#: first or the COG layer fails with "GeoTIFF is not defined".
DEFAULT_GEOTIFF_VERSION = "2.1.3"
CDN_ASSETS = {
    "ol_js": f"https://cdn.jsdelivr.net/npm/ol@{DEFAULT_OL_VERSION}/dist/ol.js",
    "ol_css": f"https://cdn.jsdelivr.net/npm/ol@{DEFAULT_OL_VERSION}/ol.css",
    "gt_js": (
        f"https://cdn.jsdelivr.net/npm/geotiff@{DEFAULT_GEOTIFF_VERSION}"
        "/dist-browser/geotiff.js"
    ),
}

_TEMPLATE_FILE = "template.json"
_VIEWER_FILE = "viewer.html"
_VIEWER_JS_FILE = "viewer.js"
_USER_CSS_FILE = "viewer.css"

#: The shipped, **shared** viewer runtime. The page shell (``viewer.html``) carries
#: only the markup + a tiny bootstrap that injects the per-map values into
#: ``window.GP_VIEWER``; all drawing logic lives here so several page shells share
#: one runtime. Served at ``/viewer/asset/viewer.js``; overridable by a Tier-2
#: ``viewer.js`` in the user templates dir.
_VIEWER_JS_ASSET = "/viewer/asset/viewer.js"

#: Every ``__...__`` placeholder the shipped page substitutes. ``__TITLE__`` etc.
#: are cosmetic; the required subset below is what the inline script needs to run.
VIEWER_PLACEHOLDERS = (
    "__TITLE__",
    "__SUBTITLE__",
    "__FOOTER__",
    "__OL_JS__",
    "__OL_CSS__",
    "__GT_JS__",
    "__VIEWER_JS__",
    "__USER_CSS_LINK__",
    "__CSS_VARS__",
    "__TEMPLATE_JSON__",
    "__MANIFEST_URL__",
    "__TOKEN_EMBEDDED__",
)

#: A user ``viewer.html`` missing any of these would produce a non-functional
#: page (undefined script constants), so :func:`load_viewer_html` refuses it.
REQUIRED_VIEWER_PLACEHOLDERS = (
    "__TEMPLATE_JSON__",
    "__MANIFEST_URL__",
    "__TOKEN_EMBEDDED__",
)

#: Top-level template keys → the value kind the default declares.
_KINDS = {
    "templateVersion": "int",
    "title": "str",
    "subtitle": "str",
    "footer": "str",
    "basemap": "str",
    "basemaps": "arr",
    "view": "obj",
    "palette": "obj",
    "layerStyle": "obj",
    "layerPalette": "arr",
    "layerList": "bool",
    "legend": "bool",
    "scale": "bool",
    "attribution": "bool",
}


def default_template() -> Dict[str, Any]:
    with open(os.path.join(DEFAULT_TEMPLATES_DIR, _TEMPLATE_FILE), encoding="utf-8") as handle:
        return json.load(handle)


def user_templates_dir(env: Optional[str] = None) -> str:
    """The Tier-2 directory: ``GEOPACK_MCP_MAP_TEMPLATES`` or ``~/.geopack/mcp/maps``."""
    configured = env if env is not None else os.getenv("GEOPACK_MCP_MAP_TEMPLATES")
    if configured and configured.strip():
        return os.path.expanduser(configured.strip())
    return os.path.join(os.path.expanduser("~"), ".geopack", "mcp", "maps")


def template_path(templates_dir: Optional[str]) -> Optional[str]:
    """Where the user edits their template (returned by ``show_map`` even if absent)."""
    if not templates_dir:
        return None
    return os.path.join(templates_dir, _TEMPLATE_FILE)


def default_viewer_html() -> str:
    """The shipped viewer page (a resource file, read from disk)."""
    with open(os.path.join(DEFAULT_TEMPLATES_DIR, _VIEWER_FILE), encoding="utf-8") as handle:
        return handle.read()


def viewer_html_path(templates_dir: Optional[str]) -> Optional[str]:
    """Where the user may drop-in their own page (returned by ``show_map``)."""
    if not templates_dir:
        return None
    return os.path.join(templates_dir, _VIEWER_FILE)


def default_viewer_js() -> str:
    """The shipped shared viewer runtime (a resource file, read from disk)."""
    with open(os.path.join(DEFAULT_TEMPLATES_DIR, _VIEWER_JS_FILE), encoding="utf-8") as handle:
        return handle.read()


def viewer_js_path(templates_dir: Optional[str]) -> Optional[str]:
    """Where a user may override the shared runtime (returned by ``show_map``)."""
    if not templates_dir:
        return None
    return os.path.join(templates_dir, _VIEWER_JS_FILE)


def load_viewer_html(templates_dir: Optional[str] = None) -> Tuple[str, str, List[str]]:
    """The page to render: ``(html_text, source, warnings)``.

    ``source`` is ``"user"`` when a Tier-2 ``viewer.html`` was used, else
    ``"default"``. A user page missing a required ``__…__`` placeholder is unsafe
    to render (its inline script would reference undefined constants), so the
    shipped page is used instead and a warning recorded.
    """
    warnings: List[str] = []
    path = viewer_html_path(templates_dir)
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            warnings.append(
                f"viewer.html could not be read ({exc.__class__.__name__}); using the default page."
            )
            return default_viewer_html(), "default", warnings
        missing = [tok for tok in REQUIRED_VIEWER_PLACEHOLDERS if tok not in text]
        if missing:
            warnings.append(
                "viewer.html is missing required placeholder(s) "
                + ", ".join(missing)
                + "; using the default page."
            )
            return default_viewer_html(), "default", warnings
        return text, "user", warnings
    return default_viewer_html(), "default", warnings


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "obj"
    if isinstance(value, list):
        return "arr"
    return type(value).__name__


def _merge_checked(base: Dict[str, Any], overlay: Dict[str, Any],
                   warnings: List[str], prefix: str = "") -> None:
    for key, value in overlay.items():
        where = f"{prefix}{key}"
        if key not in base:
            warnings.append(f"unknown template key '{where}' ignored.")
            continue
        current = base[key]
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_checked(current, value, warnings, prefix=f"{where}.")
            continue
        if _kind_of(value) != _kind_of(current):
            warnings.append(
                f"template key '{where}' expects {_kind_of(current)}, got "
                f"{_kind_of(value)}; using the default."
            )
            continue
        base[key] = copy.deepcopy(value)


def load_template(templates_dir: Optional[str] = None,
                  per_call: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], List[str], str]:
    """Merge the three tiers; return ``(template, warnings, source)``.

    ``source`` is ``"default"`` / ``"user"`` / ``"call"`` (the highest tier that
    contributed).
    """
    template = default_template()
    warnings: List[str] = []
    source = "default"

    path = template_path(templates_dir)
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                user = json.load(handle)
        except (OSError, ValueError) as exc:  # noqa: BLE001 - never fatal
            warnings.append(
                f"template.json could not be read ({exc.__class__.__name__}); using defaults."
            )
            user = None
        if isinstance(user, dict):
            _merge_checked(template, user, warnings)
            source = "user"
        elif user is not None:
            warnings.append("template.json is not a JSON object; ignored.")

    if isinstance(per_call, dict) and per_call:
        _merge_checked(template, per_call, warnings)
        if source == "default":
            source = "call"

    return template, warnings, source


def resolve_basemap(template: Dict[str, Any], name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The selected basemap entry (``None`` when the template declares none/blank)."""
    basemaps = [b for b in (template.get("basemaps") or []) if isinstance(b, dict)]
    wanted = name if name is not None else template.get("basemap")
    if wanted:
        for entry in basemaps:
            if entry.get("id") == wanted:
                return entry
    return basemaps[0] if basemaps else None


def _css_vars(palette: Dict[str, Any]) -> str:
    mapping = {
        "header": "--gp-header",
        "accent": "--gp-accent",
        "text": "--gp-text",
        "panel": "--gp-panel",
    }
    lines = []
    for key, var in mapping.items():
        value = palette.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"    {var}: {value.strip()};")
    return "\n".join(lines)


def render_viewer_html(*, title: str, manifest_url: str, template: Dict[str, Any],
                       assets: Dict[str, str], user_css: Optional[str] = None,
                       embedded_token: Optional[str] = None,
                       html_template: Optional[str] = None) -> str:
    """Render the viewer page for one map.

    ``html_template`` is the page resource (:func:`load_viewer_html`); when
    ``None`` the shipped default is read. ``user_css`` is a URL to a Tier-2
    ``viewer.css`` (link href), or ``None``. ``embedded_token`` (only a token the
    server already validated) is baked into the page so it does not depend on the
    URL query/fragment, which some hosts drop.
    """
    subtitle = template.get("subtitle") or ""
    footer = template.get("footer") or ""
    user_css_link = f'<link rel="stylesheet" href="{html.escape(user_css)}">' if user_css else ""

    def script_json(value: Any) -> str:
        # `</script>` inside a JSON string must not close the block.
        return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

    html_text = html_template if html_template is not None else default_viewer_html()
    for token, value in (
        ("__TITLE__", html.escape(str(title))),
        ("__SUBTITLE__", html.escape(str(subtitle))),
        ("__FOOTER__", html.escape(str(footer))),
        ("__OL_JS__", html.escape(assets.get("ol_js", CDN_ASSETS["ol_js"]))),
        ("__OL_CSS__", html.escape(assets.get("ol_css", CDN_ASSETS["ol_css"]))),
        ("__GT_JS__", html.escape(assets.get("gt_js", CDN_ASSETS["gt_js"]))),
        ("__VIEWER_JS__", html.escape(assets.get("viewer_js", _VIEWER_JS_ASSET))),
        ("__MANIFEST_URL__", script_json(manifest_url)),
        ("__TOKEN_EMBEDDED__", script_json(embedded_token or "")),
        ("__TEMPLATE_JSON__", script_json(template)),
        ("__CSS_VARS__", _css_vars(template.get("palette") or {})),
        ("__USER_CSS_LINK__", user_css_link),
    ):
        html_text = html_text.replace(token, value)
    return html_text
