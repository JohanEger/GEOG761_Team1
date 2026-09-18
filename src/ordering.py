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
"""

from pathlib import Path


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
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError


def place_order(order_request: dict) -> str:
    """Submit the order and return its order ID.

    Log the order in docs/data_catalogue.csv immediately, including the estimated
    area consumed. Not afterwards — within a month nobody will remember whether a
    coverage gap is missing data or a failed delivery.
    """
    raise NotImplementedError


def poll_order(order_id: str, timeout_s: int = 7200) -> str:
    """Poll until the order succeeds or fails. Returns the final state.

    Delivery to GEE is asynchronous: a successful order state does not always mean
    every asset has finished ingesting. Verify against the collection itself.
    """
    raise NotImplementedError


def verify_delivery(collection: str, expected_item_ids: list[str]) -> list[str]:
    """List item IDs missing from the GEE collection after an order completes.

    Returns the IDs that did not arrive, so they can be re-ordered deliberately
    rather than discovered as gaps months later.
    """
    raise NotImplementedError


def log_order(catalogue_path: Path, row: dict) -> None:
    """Append one row to docs/data_catalogue.csv."""
    raise NotImplementedError
