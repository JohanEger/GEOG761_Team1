# Approach 2: Statistical detection and classification in PlanetScope time series

Detection of small vessels in Nuku'alofa harbour from a PlanetScope time series (2019–2026), using a per-pixel background model to find bright anomalies and a random forest to separate vessels from false alarms.

· Notebooks: `notebooks/johan/` 

· Labels: `labels/ps_labels.geojson` 

· AOIs: `aoi/Nukualofa_wharf.geojson`, `aoi/analysis_zone.geojson` 

· Decisions: [`decisions.md`](decisions.md) 

· Labelling rules: [`labelling-guide.md`](labelling-guide.md)

## Workflow

A two-stage pipeline, run in Google Earth Engine from Colab. No imagery is downloaded for detection or classification; everything except the labelling GeoTIFFs and figures is computed server-side.

1. **Ordering** — `order_planet_gee_batch.ipynb`
   Reads scene IDs from `docs/scene_selection.xlsx` and orders PlanetScope 4-band surface reflectance + UDM2, clipped to `aoi/Nukualofa_wharf.geojson`, delivered straight into an Earth Engine collection. 29 scenes → 27 acquisitions (split passes from the same satellite and date are mosaicked).

2. **Candidate detection** — `candidate_detection.ipynb`
   - Cloud mask from UDM2 (cloud, shadow, heavy haze) with a 30 m buffer; acquisitions with < 30 % clear water dropped.
   - Detection area: ESA WorldCover water widened by 20 m, restricted to `aoi/analysis_zone.geojson` and to pixels with ≥ 5 clear background dates.
   - Background model per pixel: 25th percentile of scene-normalised NIR across the background acquisitions; noise = IQR / 1.349, smoothed, floored and capped.
   - Score = (scene − background) / noise, then centred and scaled per scene. Pixels with score ≥ 6 form candidates.
   - Exports candidate points and creates the labelling layer.

3. **Labelling** (QGIS, see [`labelling-guide.md`](labelling-guide.md))
   Candidates in the training acquisitions classified as vessel / vessel_uncertain / wake / false_positive; three test acquisitions labelled exhaustively.

4. **Classification and evaluation** — `candidate_classifier.ipynb`
   - Features per candidate sampled in Earth Engine (anomaly scores, local clutter, per-band contrast, NDWI, distance to cloud, haze, satellite generation).
   - Random forest, cross-validated with whole scenes held out (`StratifiedGroupKFold` by acquisition).
   - Evaluation of detector + classifier against the test acquisitions, miss-reason diagnostics, and a detection density map.
   - Produces the report figures.

## Results (variant C, see the classifier notebook)

| | Value |
|---|---|
| Classifier, grouped CV on 420 labelled candidates (13 scenes) | AP 0.82 (random 0.27), ROC AUC 0.91 |
| Operating point (best-F1 threshold p ≥ 0.40) | precision 0.74, recall 0.76 on candidates |
| Test scenes, 24 boats in the analysis area and cloud-free | detector alone: recall 13/24; detector + classifier: recall 12/24, precision 12/178 |

On the test scenes the classifier keeps almost all detected boats while cutting candidates from 4028 to 178, but end-to-end recall is limited by the detector: of 39 test boats, 12 were outside the detection water, 3 cloud-masked, and 10 had a candidate more than 6 m away (often a boat merged with a bright wharf or shoreline into one large blob).

## Reproducing

Imagery is not included (see licensing in the main README). To re-run the notebooks you need:
- PlanetScope access (e.g. Planet's Education and Research programme) and a Planet API key, stored as the Colab secret `PL_API_KEY`;
- a Google Cloud project with the Earth Engine API enabled, and a base64 service-account key for Planet's Earth Engine delivery, stored as `PLANET_GEE_SA`.

Set `GEE_PROJECT` in the first cell of each notebook, then run them in order. Paths to Drive outputs are set in each notebook's settings cell.

## Known gaps

- The cell that aggregates detections to the 100 m grid for the density map (`grid`, `n_scenes`) is not in the classifier notebook; the map cell depends on it.
- Variants A and B in the results figure were produced by earlier runs with different settings; see the markdown cell above that figure.