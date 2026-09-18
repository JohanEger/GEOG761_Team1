"""Aggregate detections into grids and heat maps.


Runs partly in Earth Engine (clear-observation counting over the full collection) and
partly locally (joining detections to the grid, cartography). Detections arrive as a
GeoJSON of points exported from candidates.py and filtered by classify.py.

The key correction: normalise by the number of CLEAR observations per cell, not by the
number of scenes. Cloudier areas are imaged less often and would otherwise appear to
have less vessel traffic than they really do.
"""

from pathlib import Path
import numpy as np


def build_grid(aoi_geojson: dict, cell_km: float = 1.0,
               crs: str = "EPSG:5887"):
    """Create the analysis grid over the AOI. Returns a GeoDataFrame."""
    raise NotImplementedError


def count_detections(grid, detections) -> np.ndarray:
    """Count confirmed detections falling in each grid cell."""
    raise NotImplementedError


def clear_observations_per_cell(grid, clear_count_raster: Path) -> np.ndarray:
    """Mean clear-observation count per cell.

    The raster comes from preprocess.clear_observation_count(), exported from
    Earth Engine.
    """
    raise NotImplementedError


def activity_rate(counts: np.ndarray, clear_obs: np.ndarray,
                  min_obs: int = 5) -> np.ndarray:
    """Detections per clear observation.

    Cells with fewer than min_obs clear observations return NaN rather than a
    misleadingly precise rate from two cloudy glimpses.
    """
    raise NotImplementedError


def seasonal_split(detections, season_months: dict) -> dict:
    """Split detections by season (e.g. cyclone season vs rest of year).

    Each split must be normalised by its OWN clear-observation count — cloud cover
    differs sharply between seasons, which is exactly the bias this guards against.
    """
    raise NotImplementedError


def write_heatmap(grid, values: np.ndarray, out_path: Path) -> None:
    """Write the heat map as a GeoTIFF in EPSG:5887, for QGIS or ArcGIS Pro."""
    raise NotImplementedError
