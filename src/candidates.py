"""Candidate vessel detection via temporal background subtraction — in Earth Engine.


Approach: boats are transient, reefs and rocks are not. Build a per-pixel median across
the masked collection, then flag pixels in each scene that are significantly brighter
than that background. NIR gives the strongest contrast against water.

Keep the threshold loose. Recall here matters more than precision, because the patch
classifier filters afterwards and anything missed at this stage can never be recovered.
The trade-off is that the final recall figure is conditional on this step — so label a
few scenes exhaustively by hand to measure what candidate detection itself misses.

Output is a FeatureCollection of candidate points, exported to Drive for labelling.
Rasters stay in Earth Engine; only points and small patches come down.
"""

import ee


def temporal_median(collection: "ee.ImageCollection", band: str = "nir",
                    window: int = 25) -> "ee.Image":
    """Per-pixel median background from the masked collection.

    Roughly 20-30 scenes is enough for a stable median. More is not better: a longer
    window spanning seasons blurs genuine changes in water brightness.
    """
    raise NotImplementedError


def detect_anomalies(image: "ee.Image", background: "ee.Image",
                     threshold_sigma: float = 4.0,
                     band: str = "nir") -> "ee.Image":
    """Flag pixels significantly brighter than the background.

    Returns a binary mask. Threshold is in standard deviations of the per-pixel
    residual distribution over water.
    """
    raise NotImplementedError


def to_candidate_points(mask: "ee.Image", image: "ee.Image", aoi: "ee.Geometry",
                        scale: float = 3.0,
                        min_area_px: int = 1) -> "ee.FeatureCollection":
    """Convert an anomaly mask into candidate points.

    Each feature carries: coordinates, scene ID, acquisition datetime, peak value,
    residual in sigma, and pixel area. All of it is needed later — provenance is what
    makes a label reusable when the patch size or model changes.
    """
    raise NotImplementedError


def apply_exclusions(candidates: "ee.FeatureCollection",
                     exclusions: "ee.FeatureCollection",
                     radius_m: float = 15) -> "ee.FeatureCollection":
    """Drop candidates falling on known fixed features.

    Exclusion lists are built once per harbour by inspecting high-resolution reference
    imagery: wharves, permanent moorings, navigation marks, rocks that break the
    surface. Maxar Open Data covers Nuku'alofa (January 2022); elsewhere use Esri
    Wayback or Google Earth for visual reference only — neither may be used as
    training data.
    """
    raise NotImplementedError


def run_detection(collection: "ee.ImageCollection", aoi: "ee.Geometry",
                  exclusions: "ee.FeatureCollection",
                  cfg: dict) -> "ee.FeatureCollection":
    """Full candidate detection across a preprocessed collection.

    Returns candidate points for every scene, ready to export for labelling or to
    pass to the classifier.
    """
    raise NotImplementedError


def export_patches(candidates: "ee.FeatureCollection",
                   collection: "ee.ImageCollection",
                   patch_size: int, folder: str) -> None:
    """Export fixed-size image patches around each candidate, for labelling.

    Earth Engine cannot train a CNN, so patches come down to Drive and the classifier
    runs in Colab. Export the median background patch alongside each candidate patch:
    annotators need to see both to judge whether something is transient.
    """
    raise NotImplementedError
