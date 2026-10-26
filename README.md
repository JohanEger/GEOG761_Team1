# Tonga-Vessels: a recognised maritime picture of small-vessel activity in Tongan waters

GEOG761 group project, University of Auckland, 2026.

## Motivation

When cyclones, tsunamis or volcanic activity damage primary ports, small vessels become an important way of delivering aid, and there is little systematic knowledge of where they operate. This project tests two ways of detecting small vessels in satellite imagery of Tongan harbours, with Nuku'alofa as the main study area, and maps where they are active.

## Approaches

| | Approach | Data | Documentation |
|---|---|---|---|
| 1 | Detecting and mapping vessel activity using OBB deep learning (YOLO11-OBB, fine-tuned on DOTA v1.5) | Maxar Open Data: WorldView-2/3, 0.4–0.5 m. Nuku'alofa (Jan 2022) and Port Vila, Vanuatu (Sep–Oct 2024) | [`docs/approach1-yolo.md`](docs/approach1-yolo.md) *(to be added)* |
| 2 | Statistical anomaly detection + random-forest classification in a PlanetScope time series | PlanetScope 3 m, 2019–2026 | [`docs/approach2-planetscope.md`](docs/approach2-planetscope.md) |

Port Vila is used as a test site for Approach 1 because Maxar Open Data
provides three recent high-resolution scenes of a busy Pacific harbour there.

## Repository layout

```
aoi/
  analysis_zone.geojson     Tonga analysis zones
  Nukualofa_wharf.geojson   Nuku'alofa wharf polygons
  AOI_Vanuatu.geojson       Port Vila study area (Approach 1)
  VENUATUPolygon.geojson    Vanuatu land polygons, used to mask detections on land
docs/
  approach1-yolo.md     Approach 1 workflow (to be added)
  approach2-planetscope.md  Approach 2 workflow, results, reproduction
  decisions.md          method decisions log
  labelling-guide.md    PlanetScope labelling rules and label schema
  scene_selection.xlsx  PlanetScope scene list used for ordering
labels/
  ps_labels.geojson     PlanetScope labels (Approach 2), EPSG:32701
notebooks/
  alex/
    Shipdetection_dota.ipynb        Approach 1: fine-tuning YOLO11-OBB on DOTA v1.5
  johan/
    candidate_detection.ipynb       Approach 2: anomaly-based candidate detection
    candidate_classifier.ipynb      Approach 2: random-forest classification
    order_planet_gee_batch.ipynb    Approach 2: PlanetScope ordering via Earth Engine
    maxar_vessel_inference.ipynb    Approach 1: inference on Maxar imagery, Nuku'alofa
    flowchart.py                    workflow diagram
  niamh/
    vanuatu_obb_detection.ipynb     Approach 1: detection and density maps, Port Vila
```

## Licensing and attribution

- **Code:** MIT (see `LICENSE`), except the notebooks that use Ultralytics YOLO,
  which are licensed AGPL-3.0 (see `LICENSE-AGPL`):
  `notebooks/alex/Shipdetection_dota.ipynb`,
  `notebooks/johan/maxar_vessel_inference.ipynb` and
  `notebooks/niamh/vanuatu_obb_detection.ipynb`.
- **Model weights** (fine-tuned YOLO11-OBB) are not included.
- **Labels and AOIs** (`labels/`, `aoi/`): CC BY 4.0. Labels were made by visual
  interpretation of satellite imagery and contain point locations, scores and
  classes only — no image values.
- **PlanetScope imagery** © Planet Labs PBC, used under Planet's Education and
  Research programme. Imagery and datasets containing image values are not
  redistributed here; figures in the notebooks are rendered images only.
- **Maxar imagery** © Maxar Technologies, Maxar Open Data Program, CC BY-NC 4.0.
  Used for vessel detection (Approach 1) and comparison figures, and streamed
  from the Maxar Open Data bucket. Not included in the repository. Figures and
  results derived from it are shared under CC BY-NC 4.0.
- **Water mask (Tonga):** ESA WorldCover 10 m 2021 v200, © ESA WorldCover
  project, CC BY 4.0.

## References

- Ultralytics YOLO11: https://github.com/ultralytics/ultralytics
- DOTA dataset: https://captain-whu.github.io/DOTA/
- Maxar Open Data Program: https://www.maxar.com/open-data
- ESA WorldCover 2021 v200: https://esa-worldcover.org

Full citations are in the project report.