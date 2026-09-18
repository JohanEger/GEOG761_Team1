"""Cloud masking, land masking and scene quality filtering — in Earth Engine.

Everything here runs server-side on the delivered PlanetScope collection. Nothing is
downloaded. The output is a filtered, masked ee.ImageCollection that candidates.py
consumes directly.

Notes:
- Cloud, haze and shadow information comes from the udm2 bands delivered with each
  scene. Confirm the band names on an actual delivered asset before assuming them —
  they differ from the standalone udm2 asset naming in places.
- Land masking matters more than it sounds. Almost every bright anomaly over land is
  irrelevant, and shoreline glare is a large false-positive source, hence the inward
  buffer on the coastline.
- Co-registration is handled at order time by reprojecting every scene onto the same
  EPSG:5887 grid, so no per-scene alignment step is needed here. Verify this holds on
  a sample of scenes before trusting it: a consistent one-pixel offset between dates
  would corrupt the temporal median and create false candidates along every edge.
"""

import ee


def mask_clouds(image: "ee.Image", cfg: dict) -> "ee.Image":
    """Mask cloudy, hazy and shadowed pixels using the udm2 bands.

    Returns the image with unusable pixels masked, so Earth Engine reducers skip
    them automatically.
    """
    raise NotImplementedError


def mask_land(image: "ee.Image", coastline: "ee.FeatureCollection",
              buffer_m: float = 30) -> "ee.Image":
    """Mask land and a buffer inward from the coastline.

    The buffer removes shoreline glare and beached-object false positives. Widen it
    if the shoreline generates persistent candidates; narrow it if boats moored close
    against a wharf are being lost.
    """
    raise NotImplementedError


def clear_water_fraction(image: "ee.Image", aoi: "ee.Geometry",
                         scale: float = 3.0) -> "ee.Number":
    """Fraction of water pixels in the AOI that are usable in this scene.

    Used to drop scenes too cloudy to contribute, and — importantly — to count clear
    observations per grid cell later, which is what the heat map is normalised by.
    """
    raise NotImplementedError


def prepare_collection(collection: "ee.ImageCollection", aoi: "ee.Geometry",
                       coastline: "ee.FeatureCollection",
                       cfg: dict) -> "ee.ImageCollection":
    """Full preprocessing chain: mask clouds, mask land, drop unusable scenes.

    Returns a collection ready for temporal background subtraction, with a
    'clear_fraction' property set on every image.
    """
    raise NotImplementedError


def clear_observation_count(collection: "ee.ImageCollection") -> "ee.Image":
    """Per-pixel count of clear observations across the collection.

    This raster is what aggregate.py divides detections by. Without it, frequently
    cloud-free areas look busier simply because they were observed more often.
    """
    raise NotImplementedError
