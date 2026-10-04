"""Planet search and ordering, with delivery straight into Google Earth Engine.

Under the Basic Education & Research licence, GEE deliveries count against the monthly
download allowance, so quota — not storage — is the binding constraint. Plan orders in
area, not in scene count, and log consumption in docs/data_catalogue.csv as you go.

Before the first order:
- The destination GEE ImageCollection must already exist:
      earthengine create collection projects/<project>/assets/tonga_psscene
- The Earth Engine API must be enabled on the Cloud project.
- Planet's service account needs permission to write into the project.
- Test with ONE scene before placing a large order. A failed delivery caused by a
  permissions or path error spends quota twice.

Do not re-order a scene that is already in the collection. Assets persist, so decide
clipping and reprojection parameters before ordering rather than redoing them later.

Two logs, both in docs/ and both committed:
- ordered_scenes.csv: one row per scene per order. Check it before ordering;
  place_order() refuses scenes it already holds for the same AOI.
- data_catalogue.csv: one row per order, with the quota it used.

scripts/order_scenes.py wraps check -> order -> log -> status for the command line.
The Planet API key comes from PL_API_KEY (environment or Colab Secrets), never a cell.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import transform

from src.config import REPO_ROOT

DATA_API = "https://api.planet.com/data/v1"
ORDERS_API = "https://api.planet.com/compute/ops/orders/v2"

LEDGER = REPO_ROOT / "docs" / "ordered_scenes.csv"
CATALOGUE = REPO_ROOT / "docs" / "data_catalogue.csv"
LEDGER_FIELDS = ["item_id", "aoi", "product_bundle", "est_km2", "order_id", "order_name",
                 "ordered_by", "ordered_at_utc", "state", "notes"]

# Orders API states. Scenes in a failed or cancelled order may be ordered again; any
# other state means the scene is taken.
FINAL_STATES = {"success", "partial", "failed", "cancelled"}
REORDERABLE_STATES = {"failed", "cancelled"}

# Assets each product bundle needs, to check before ordering that a scene can be
# delivered as that bundle. Only SuperDove (PSB.SD) scenes have 8-band products;
# Dove Classic (PS2) and Dove-R (PS2.SD) scenes are 4-band.
BUNDLE_ASSETS = {
    "analytic_8b_sr_udm2": ("ortho_analytic_8b_sr", "ortho_udm2"),
    "analytic_8b_udm2": ("ortho_analytic_8b", "ortho_udm2"),
    "analytic_sr_udm2": ("ortho_analytic_4b_sr", "ortho_udm2"),
    "analytic_udm2": ("ortho_analytic_4b", "ortho_udm2"),
}

# Planet's reproject tool takes GDAL kernel names; config may use the plain-English one.
KERNEL_ALIASES = {"nearest": "near", "nearest_neighbour": "near", "nearest_neighbor": "near"}

# 20190623_213507_1054 (Dove Classic) or 20250110_220650_09_24dd (Dove-R, SuperDove).
ITEM_ID_RE = re.compile(r"^(\d{8})_(\d{6})(?:_(\d{2}))?_([0-9a-f]{4})$")


# --------------------------------------------------------------------------
# Planet API access
# --------------------------------------------------------------------------

def planet_session(api_key: str | None = None):
    """Authenticated requests session for Planet's APIs.

    The key comes from the argument, the PL_API_KEY environment variable or Colab
    Secrets, in that order.
    """
    import requests

    key = api_key or os.environ.get("PL_API_KEY")
    if not key:
        try:
            from google.colab import userdata          # running in Colab
            key = userdata.get("PL_API_KEY")
        except Exception:
            key = None
    if not key:
        raise RuntimeError("No Planet API key. Set PL_API_KEY in the environment "
                           "or in Colab Secrets.")
    session = requests.Session()
    session.auth = (key, "")
    return session


def _request(session, method: str, url: str, retry_server_errors: bool = True,
             **kwargs):
    """Send a request, backing off when rate limited.

    Server errors are retried only when asked: retrying a POST the server may already
    have processed could place the same order twice.
    """
    for attempt in range(6):
        r = session.request(method, url, timeout=60, **kwargs)
        if not (r.status_code == 429 or (retry_server_errors and r.status_code >= 500)):
            break
        time.sleep(min(2 ** attempt, 30))
    if r.status_code == 401:
        raise RuntimeError("Planet rejected the API key (401). Check PL_API_KEY.")
    return r


def get_order(session, order_id: str) -> dict:
    """The order as Planet currently reports it."""
    r = _request(session, "GET", f"{ORDERS_API}/{order_id}")
    r.raise_for_status()
    return r.json()


# --------------------------------------------------------------------------
# Scene IDs, AOIs and area
# --------------------------------------------------------------------------

def parse_item_id(item_id: str) -> dict | None:
    """Acquisition time and satellite from a PSScene ID, or None if it is malformed.

    A format check only, which needs no API key. check_items() asks Planet whether
    the scene actually exists.
    """
    m = ITEM_ID_RE.match(item_id)
    if not m:
        return None
    day, hms, fraction, satellite = m.groups()
    try:
        acquired = datetime.strptime(day + hms, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    # IDs without the hundredths-of-a-second part are Dove Classic: 4-band only.
    return {"acquired_utc": acquired, "satellite_id": satellite,
            "dove_classic": fraction is None}


def load_aoi_file(path: str | Path) -> tuple[str, dict]:
    """(name, WGS84 geometry) from an AOI GeoJSON. The name is the file stem."""
    path = Path(path)
    gj = json.loads(path.read_text(encoding="utf-8"))
    if gj.get("type") == "FeatureCollection":
        if len(gj["features"]) != 1:
            raise ValueError(f"{path.name} holds {len(gj['features'])} features; "
                             "AOI files should hold exactly one")
        gj = gj["features"][0]
    if gj.get("type") == "Feature":
        gj = gj["geometry"]
    return path.stem, gj


@lru_cache(maxsize=None)
def _to_crs(crs: str):
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform


def _projected(geometry: dict, crs: str):
    return make_valid(transform(_to_crs(crs), shape(geometry)))


def area_km2(geometry: dict, crs: str = "EPSG:5887") -> float:
    """Area of a WGS84 GeoJSON geometry, measured in the project grid."""
    return _projected(geometry, crs).area / 1e6


def clipped_area(footprint: dict, aoi: dict,
                 crs: str = "EPSG:5887") -> tuple[float, float]:
    """(km² of the AOI inside a scene footprint, % of the AOI it covers).

    The first number is what a clipped order of that scene costs, if Planet charges
    on the clipped area (config: quota.charged_on).
    """
    aoi_m = _projected(aoi, crs)
    inside = _projected(footprint, crs).intersection(aoi_m).area
    return inside / 1e6, 100 * inside / aoi_m.area


def search_scenes(aoi_geojson: dict, start_date: str, end_date: str,
                  max_cloud_cover: float = 0.4,
                  item_type: str = "PSScene") -> list[dict]:
    """Search the Planet catalogue and return matching scene metadata.

    Args:
        aoi_geojson: AOI geometry as a GeoJSON dict (WGS84).
        start_date, end_date: ISO dates, e.g. "2022-01-01".
        max_cloud_cover: fraction, 0-1.
        item_type: Planet item type.

    Returns:
        List of scene metadata dicts including item ID, acquisition datetime and
        cloud cover.
    """
    raise NotImplementedError


def estimate_quota(aoi_geojson: dict, n_scenes: int, crs: str = "EPSG:5887") -> float:
    """Estimate quota consumption in km² for a planned order.

    Call this BEFORE placing any order. Whether quota is charged on the clipped area
    or the full scene footprint is recorded in config under quota.charged_on — confirm
    it with Planet support, because it decides whether tighter AOIs or fewer dates is
    the better economy.

    This is the upper bound for a clipped order: AOI area times scene count, as if
    every scene covered the whole AOI. check_items() gives the figure per scene.
    """
    return area_km2(aoi_geojson, crs) * n_scenes


def bundle_available(item: dict, bundle: str) -> bool | None:
    """Whether this account can order `bundle` for the item.

    Reads the item's _permissions (the assets this account may download), falling
    back on its asset list. None when it cannot tell: an unknown bundle, or an item
    record with neither field.
    """
    needed = BUNDLE_ASSETS.get(bundle)
    if needed is None:
        return None
    if "_permissions" in item:
        have = {p.split(":")[0].removeprefix("assets.") for p in item["_permissions"]}
    elif item.get("assets"):
        have = set(item["assets"])
    else:
        return None
    return all(asset in have for asset in needed)


def check_items(session, item_ids: list[str], aoi_geojson: dict, bundle: str,
                item_type: str = "PSScene", crs: str = "EPSG:5887") -> list[dict]:
    """Look each scene up in Planet's catalogue. Orders nothing and uses no quota.

    One row per ID: status (ok, not_found, no_access, no_bundle, outside_aoi),
    instrument, acquisition time, scene cloud cover, the share of the AOI the scene
    covers, and the clipped area an order of it would charge.
    """
    rows = []
    for item_id in item_ids:
        row = {"item_id": item_id, "status": "", "instrument": "", "acquired_utc": "",
               "cloud_cover": "", "aoi_coverage_pct": "", "est_km2": ""}
        r = _request(session, "GET", f"{DATA_API}/item-types/{item_type}/items/{item_id}")
        if r.status_code in (403, 404):
            row["status"] = "not_found" if r.status_code == 404 else "no_access"
            rows.append(row)
            continue
        r.raise_for_status()
        item = r.json()
        props = item.get("properties", {})
        km2, pct = clipped_area(item["geometry"], aoi_geojson, crs)
        row.update(instrument=props.get("instrument", ""),
                   acquired_utc=props.get("acquired", ""),
                   cloud_cover=props.get("cloud_cover", ""),
                   aoi_coverage_pct=round(pct, 1), est_km2=round(km2, 2))
        if bundle_available(item, bundle) is False:
            row["status"] = "no_bundle"
        elif km2 == 0:
            row["status"] = "outside_aoi"
        else:
            row["status"] = "ok"
        rows.append(row)
    return rows


def select_scenes(scenes: list[dict], mode: str = "dense",
                  per_week: int = 3) -> list[dict]:
    """Choose which scenes to order within the quota budget.

    mode="dense": every usable scene. Use for the method-development AOI only.
    mode="sampled": roughly `per_week` clear scenes per week, spread through the
        week rather than clustered, so seasonal and weekly patterns stay visible.

    The temporal median background needs roughly 20-30 scenes to be stable, not
    hundreds — sampling costs far less quota and loses little.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------

def gee_delivery(cfg: dict) -> dict:
    """Planet's GEE delivery block: the Cloud project ID and the collection *name*.

    Planet writes into projects/<project>/assets/<collection>. Config holds the full
    asset path, so check the two agree rather than delivering somewhere unexpected.
    """
    project = cfg["gee"]["project"]
    path = cfg["gee"]["collection"]
    prefix = f"projects/{project}/assets/"
    name = path[len(prefix):] if path.startswith(prefix) else ""
    if not name or "/" in name:
        raise ValueError(f"gee.collection should be {prefix}<name>, got {path!r}")
    return {"project": project, "collection": name}


def build_order(item_ids: list[str], aoi_geojson: dict, cfg: dict,
                name: str) -> dict:
    """Build the Orders API request: clip, reproject, deliver to GEE.

    The delivery and tools blocks should come out roughly as:

        {
          "name": name,
          "products": [{"item_ids": item_ids,
                        "item_type": cfg["planet"]["item_type"],
                        "product_bundle": cfg["planet"]["asset"]}],
          "tools": [{"clip": {"aoi": aoi_geojson}},
                    {"reproject": {"projection": f"EPSG:{cfg['planet']['reproject_epsg']}",
                                   "resolution": cfg["planet"]["reproject_resolution"],
                                   "kernel": cfg["planet"]["resampling"]}}],
          "delivery": {"google_earth_engine": {"project": cfg["gee"]["project"],
                                               "collection": cfg["gee"]["collection"]}},
          "notifications": {"email": True}
        }

    Check the current Orders API reference for exact tool parameter names before
    relying on this.

    Clip runs before reproject, so only the AOI is resampled. The kernel goes through
    KERNEL_ALIASES ("nearest" in config becomes GDAL's "near"), and the collection is
    passed by name (see gee_delivery). Without GEE delivery in config the order is
    left for download.
    """
    planet = cfg["planet"]
    kernel = KERNEL_ALIASES.get(planet["resampling"], planet["resampling"])
    request = {
        "name": name,
        "products": [{"item_ids": list(item_ids),
                      "item_type": planet["item_type"],
                      "product_bundle": planet["asset"]}],
        "tools": [{"clip": {"aoi": aoi_geojson}},
                  {"reproject": {"projection": f"EPSG:{planet['reproject_epsg']}",
                                 "resolution": planet["reproject_resolution"],
                                 "kernel": kernel}}],
        "notifications": {"email": True},
    }
    if planet.get("delivery") == "google_earth_engine":
        request["delivery"] = {"google_earth_engine": gee_delivery(cfg)}
    return request


def place_order(order_request: dict, *, aoi_name: str, ordered_by: str,
                est_km2: dict[str, float] | None = None, session=None,
                ledger: Path | None = None, catalogue: Path | None = None,
                allow_reorder: bool = False) -> str:
    """Submit the order and return its order ID.

    Log the order in docs/data_catalogue.csv immediately, including the estimated
    area consumed. Not afterwards — within a month nobody will remember whether a
    coverage gap is missing data or a failed delivery.

    This does that: as soon as Planet accepts the order, every scene goes into the
    ledger and the order into the catalogue. Scenes the ledger already holds for this
    AOI are refused before anything is sent, unless allow_reorder is set.

    est_km2 maps item ID to the clipped area from check_items(). Scenes without an
    estimate are logged at the full AOI area, an upper bound.
    """
    ledger, catalogue = Path(ledger or LEDGER), Path(catalogue or CATALOGUE)
    item_ids = [i for p in order_request["products"] for i in p["item_ids"]]
    same, _ = ledger_conflicts(item_ids, aoi_name, ledger)
    if same and not allow_reorder:
        raise ValueError(f"Already ordered for {aoi_name} (see {ledger.name}): "
                         + ", ".join(sorted(same)))

    session = session or planet_session()
    r = _request(session, "POST", ORDERS_API, retry_server_errors=False,
                 json=order_request)
    if not r.ok:
        raise RuntimeError(f"Planet did not accept the order ({r.status_code}): "
                           f"{r.text[:2000]}")
    order = r.json()
    try:
        _log_new_order(order, _clip_aoi(order_request), aoi_name, ordered_by, est_km2,
                       ledger, catalogue)
    except Exception as e:
        raise RuntimeError(
            f"Order {order.get('id')} WAS PLACED but logging it failed ({e}). Log it with: "
            f"python scripts/order_scenes.py record {order.get('id')} --aoi <aoi file>"
        ) from e
    return order["id"]


def record_order(order_id: str, *, aoi_name: str, ordered_by: str,
                 aoi_geojson: dict | None = None, session=None,
                 ledger: Path | None = None, catalogue: Path | None = None,
                 crs: str = "EPSG:5887") -> dict:
    """Log an order placed outside this module, e.g. in Planet's web app.

    Each scene's clipped area is estimated from its footprint (one free Data API
    lookup per scene) against aoi_geojson, or else the order's own clip AOI.
    """
    ledger, catalogue = Path(ledger or LEDGER), Path(catalogue or CATALOGUE)
    if any(r.get("order_id") == order_id for r in read_rows(ledger)):
        raise ValueError(f"Order {order_id} is already in {ledger.name}")
    session = session or planet_session()
    order = get_order(session, order_id)
    aoi = aoi_geojson or _clip_aoi(order)
    est = None
    if aoi is not None:
        est = {}
        for p in order.get("products", []):
            for row in check_items(session, p["item_ids"], aoi, p["product_bundle"],
                                   p.get("item_type", "PSScene"), crs):
                if row["est_km2"] != "":
                    est[row["item_id"]] = row["est_km2"]
    _log_new_order(order, aoi, aoi_name, ordered_by, est, ledger, catalogue)
    return order


def poll_order(order_id: str, timeout_s: int = 7200, session=None,
               interval_s: int = 60) -> str:
    """Poll until the order succeeds or fails. Returns the final state.

    Delivery to GEE is asynchronous: a successful order state does not always mean
    every asset has finished ingesting. Verify against the collection itself.

    If the timeout runs out first, returns the last state seen.
    """
    session = session or planet_session()
    deadline = time.monotonic() + timeout_s
    while True:
        state = get_order(session, order_id)["state"]
        if state in FINAL_STATES or time.monotonic() >= deadline:
            return state
        time.sleep(interval_s)


def verify_delivery(collection: str, expected_item_ids: list[str]) -> list[str]:
    """List item IDs missing from the GEE collection after an order completes.

    Returns the IDs that did not arrive, so they can be re-ordered deliberately
    rather than discovered as gaps months later.
    """
    raise NotImplementedError


def _clip_aoi(order: dict) -> dict | None:
    return next((t["clip"]["aoi"] for t in order.get("tools", []) if "clip" in t), None)


def _gee_target(order: dict) -> str:
    gee = order.get("delivery", {}).get("google_earth_engine")
    return f"projects/{gee['project']}/assets/{gee['collection']}" if gee else ""


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------

def read_rows(path: Path) -> list[dict]:
    """Rows of a CSV log; empty if the file does not exist yet."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ledger_conflicts(item_ids: list[str], aoi_name: str,
                     ledger: Path | None = None) -> tuple[dict, dict]:
    """Scenes already in the ledger: ({id: row} for this AOI, {id: [rows]} for others).

    Rows from failed or cancelled orders do not count. A hit for the same AOI is a
    duplicate. A hit for another AOI is not, but wherever the two AOIs overlap, that
    area is paid for twice.
    """
    wanted = set(item_ids)
    same, other = {}, {}
    for row in read_rows(ledger or LEDGER):
        if row.get("item_id") not in wanted or row.get("state") in REORDERABLE_STATES:
            continue
        if row.get("aoi", "").lower() == aoi_name.lower():
            same.setdefault(row["item_id"], row)
        else:
            other.setdefault(row["item_id"], []).append(row)
    return same, other


def log_order(catalogue_path: Path, row: dict) -> None:
    """Append one row to docs/data_catalogue.csv."""
    path = Path(catalogue_path)
    fields = _header(path, [])
    if not fields:
        raise FileNotFoundError(f"{path} is missing or has no header row")
    unknown = set(row) - set(fields)
    if unknown:
        raise ValueError(f"Not columns of {path.name}: {', '.join(sorted(unknown))}")
    _append_rows(path, fields, [row])


def refresh_ledger(session=None, ledger: Path | None = None,
                   catalogue: Path | None = None) -> list[tuple[str, str, str]]:
    """Update both logs with the current state of every unfinished order.

    Returns (order_id, old_state, new_state) for each order that changed. A partial
    order marks all its scenes 'partial': once verify_delivery() shows which scenes
    did not arrive, set those rows to 'failed' so they can be ordered again.
    """
    ledger, catalogue = Path(ledger or LEDGER), Path(catalogue or CATALOGUE)
    rows = read_rows(ledger)
    states = {}
    for r in rows:
        if r.get("order_id") and r.get("state") not in FINAL_STATES:
            states.setdefault(r["order_id"], r.get("state", ""))
    if not states:
        return []

    session = session or planet_session()
    changes = {}
    for order_id, old in states.items():
        new = get_order(session, order_id)["state"]
        if new != old:
            changes[order_id] = (old, new)
    if not changes:
        return []

    for r in rows:
        if r.get("order_id") in changes:
            r["state"] = changes[r["order_id"]][1]
    _rewrite_rows(ledger, _header(ledger, LEDGER_FIELDS), rows)

    delivered = {"success": "yes", "partial": "partial", "failed": "no", "cancelled": "no"}
    cat_rows = read_rows(catalogue)
    touched = False
    for r in cat_rows:
        new = changes.get(r.get("order_id"), (None, None))[1]
        if new in delivered:
            r["delivered"] = delivered[new]
            touched = True
    if touched:
        _rewrite_rows(catalogue, _header(catalogue, []), cat_rows)
    return [(order_id, old, new) for order_id, (old, new) in changes.items()]


def _log_new_order(order: dict, aoi_geojson: dict | None, aoi_name: str,
                   ordered_by: str, est_km2: dict[str, float] | None,
                   ledger: Path, catalogue: Path) -> None:
    """One ledger row per scene and one catalogue row for the order."""
    products = order.get("products", [])
    item_ids = [i for p in products for i in p["item_ids"]]
    bundle = ",".join(sorted({p["product_bundle"] for p in products}))
    aoi_km2 = area_km2(aoi_geojson) if aoi_geojson else None
    est = {i: (est_km2 or {}).get(i, aoi_km2) for i in item_ids}
    ordered_at = (order.get("created_on")
                  or datetime.now(timezone.utc).isoformat(timespec="seconds"))

    _append_rows(ledger, _header(ledger, LEDGER_FIELDS), [
        {"item_id": i, "aoi": aoi_name, "product_bundle": bundle,
         "est_km2": "" if est[i] is None else round(est[i], 2),
         "order_id": order["id"], "order_name": order.get("name", ""),
         "ordered_by": ordered_by, "ordered_at_utc": ordered_at,
         "state": order.get("state", "queued"),
         "notes": "" if est_km2 and i in est_km2 else "est_km2 is the full AOI (upper bound)"}
        for i in item_ids])

    dates = sorted(p["acquired_utc"].date().isoformat()
                   for p in map(parse_item_id, item_ids) if p)
    log_order(catalogue, {
        "order_date": ordered_at[:10], "aoi": aoi_name,
        "start_date": dates[0] if dates else "", "end_date": dates[-1] if dates else "",
        "item_type": ",".join(sorted({p.get("item_type", "") for p in products})),
        "asset": bundle, "n_scenes": len(item_ids),
        "aoi_area_km2": "" if aoi_km2 is None else round(aoi_km2, 2),
        "quota_used_km2": round(sum(v for v in est.values() if v), 2),
        "order_id": order["id"], "gee_collection": _gee_target(order),
        "delivered": "", "notes": f"quota estimated from footprints; ordered by {ordered_by}",
    })


def _header(path: Path, default: list[str]) -> list[str]:
    if path.exists() and path.stat().st_size:
        with open(path, newline="", encoding="utf-8") as f:
            return next(csv.reader(f))
    return default


def _append_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    path = Path(path)
    new = not path.exists() or path.stat().st_size == 0
    unterminated = False
    if not new:
        with open(path, "rb") as f:                  # never glue a row onto the last line
            f.seek(-1, os.SEEK_END)
            unterminated = f.read(1) not in (b"\n", b"\r")
    with open(path, "a", newline="", encoding="utf-8") as f:
        if unterminated:
            f.write("\n")
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerows(rows)


def _rewrite_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    tmp = Path(path).with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
