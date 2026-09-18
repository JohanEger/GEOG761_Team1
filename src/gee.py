"""Earth Engine session setup and shared helpers.

Every Earth Engine notebook starts with init(config). Keeping authentication and export
settings in one place means nobody hardcodes a project ID into a notebook.

Typical use:

    from src.config import load_config
    from src import gee

    config = load_config()
    gee.init(config)

    aoi = gee.aoi_to_ee(gee.load_aoi(config, "nukualofa.geojson"))
    col = gee.load_collection(config, aoi, "2022-01-01", "2022-12-31")
    print(col.size().getInfo())
"""

from __future__ import annotations

import json
from pathlib import Path

import ee


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

def init(config: dict, force_auth: bool = False) -> None:
    """Authenticate and initialise Earth Engine against the project in config.

    Safe to call repeatedly: if the session is already live, it returns immediately.
    In Colab the first call in a session opens a browser prompt.

    Args:
        config: loaded config dict.
        force_auth: re-run authentication even if a session already exists. Use when
            switching Google accounts.
    """
    project = config["gee"]["project"]

    if force_auth:
        ee.Authenticate(force=True)
        ee.Initialize(project=project)
        return

    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)

    # Fail loudly and early rather than deep inside someone's analysis.
    ee.Number(1).getInfo()


def collection_id(config: dict) -> str:
    """Full asset path of the delivered PlanetScope collection."""
    return config["gee"]["collection"]


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def load_aoi(config: dict, name: str) -> dict:
    """Read an AOI GeoJSON from the repo's aoi/ folder and return its geometry.

    Accepts a FeatureCollection, a Feature, or a bare geometry, since what comes out
    of QGIS and geojson.io differs.
    """
    from src.config import REPO_ROOT

    path = Path(REPO_ROOT) / config["paths"]["aoi_dir"] / name
    with open(path) as f:
        gj = json.load(f)

    if gj.get("type") == "FeatureCollection":
        feats = gj["features"]
        if len(feats) != 1:
            raise ValueError(
                f"{name} holds {len(feats)} features; AOI files should hold exactly one"
            )
        return feats[0]["geometry"]
    if gj.get("type") == "Feature":
        return gj["geometry"]
    return gj


def aoi_to_ee(geometry: dict) -> ee.Geometry:
    """Convert a GeoJSON geometry (WGS84) to an ee.Geometry.

    geodesic=False keeps edges as straight lines in the projected CRS, which is what
    you want for a rectangular AOI box.
    """
    return ee.Geometry(geometry, proj="EPSG:4326", geodesic=False)


# --------------------------------------------------------------------------
# Collection access
# --------------------------------------------------------------------------

def load_collection(config: dict, aoi: ee.Geometry | None = None,
                    start_date: str | None = None,
                    end_date: str | None = None) -> ee.ImageCollection:
    """Load the delivered PlanetScope collection, optionally filtered.

    Args:
        config: loaded config dict.
        aoi: restrict to images intersecting this geometry.
        start_date, end_date: ISO dates, e.g. "2022-01-01". end_date is exclusive.
    """
    col = ee.ImageCollection(collection_id(config))
    if aoi is not None:
        col = col.filterBounds(aoi)
    if start_date is not None and end_date is not None:
        col = col.filterDate(start_date, end_date)
    return col


def describe_collection(config: dict) -> dict:
    """Summarise what is actually in the collection.

    Run this after the first delivery. It returns the number of images, 
    band names, CRS and scale, and the first and last acquisition dates. 
    Useful for sanity-checking that the order was delivered correctly.
    """
    col = load_collection(config)
    n = col.size().getInfo()
    if n == 0:
        return {"n_images": 0, "note": "collection is empty — nothing delivered yet"}

    first = ee.Image(col.first())
    band_names = first.bandNames().getInfo()
    proj = first.select(0).projection()

    dates = col.aggregate_array("system:time_start").getInfo()
    dates = sorted(dates)

    return {
        "n_images": n,
        "bands": band_names,
        "crs": proj.crs().getInfo(),
        "nominal_scale_m": proj.nominalScale().getInfo(),
        "first_date": ee.Date(dates[0]).format("YYYY-MM-dd").getInfo(),
        "last_date": ee.Date(dates[-1]).format("YYYY-MM-dd").getInfo(),
        "properties": first.propertyNames().getInfo(),
    }


def list_dates(config: dict, aoi: ee.Geometry | None = None) -> list[str]:
    """Acquisition dates present in the collection, sorted. Useful for spotting gaps."""
    col = load_collection(config, aoi)
    millis = col.aggregate_array("system:time_start").getInfo()
    return sorted(
        ee.Date(m).format("YYYY-MM-dd").getInfo() for m in millis
    )


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------

def export_table(fc: ee.FeatureCollection, description: str,
                 folder: str = "tonga-vessels-exports",
                 file_format: str = "GeoJSON") -> ee.batch.Task:
    """Export a FeatureCollection to Drive.

    Used for candidate points and confirmed detections: small, and far easier to work
    with locally than pulling rasters out of Earth Engine.

    Returns the started task. Check progress with task.status(), or in the Code
    Editor's Tasks tab.
    """
    task = ee.batch.Export.table.toDrive(
        collection=fc,
        description=description,
        folder=folder,
        fileFormat=file_format,
    )
    task.start()
    return task


def export_image(image: ee.Image, description: str, region: ee.Geometry,
                 config: dict, scale: float = 3.0,
                 folder: str = "tonga-vessels-exports") -> ee.batch.Task:
    """Export a raster (heat map, background composite) to Drive as a GeoTIFF.

    Exported in the project CRS from config, so outputs drop straight into QGIS
    alongside everything else.
    """
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder=folder,
        region=region,
        scale=scale,
        crs=config["crs"],
        maxPixels=1e10,
        fileFormat="GeoTIFF",
    )
    task.start()
    return task


def task_status(tasks: list[ee.batch.Task]) -> list[dict]:
    """Compact status for a list of tasks: description, state, and any error."""
    out = []
    for t in tasks:
        s = t.status()
        out.append({
            "description": s.get("description"),
            "state": s.get("state"),
            "error": s.get("error_message"),
        })
    return out


# --------------------------------------------------------------------------
# Quick inspection
# --------------------------------------------------------------------------

def show(image: ee.Image, aoi: ee.Geometry, vis: dict | None = None,
         label: str = "image"):
    """Display an image on an interactive map in a notebook.

    Requires geemap. Returns the map object — display it as the last line of a cell.
    """
    import geemap

    m = geemap.Map()
    m.centerObject(aoi, zoom=13)
    m.addLayer(image, vis or {}, label)
    m.addLayer(ee.Image().paint(ee.FeatureCollection([ee.Feature(aoi)]), 0, 2),
               {"palette": "red"}, "AOI")
    return m
