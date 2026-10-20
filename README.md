# Tonga-Vessels: a recognised maritime picture of small-vessel activity in Tongan waters

GEOG761 group project, University of Auckland, 2026.

## Motivation

When cyclones, tsunamis or volcanic activity damage primary ports, small vessels become an important way of delivering aid, and there is little systematic knowledge of where they operate. This project tests two ways of detecting small vessels in satellite imagery of Tongan harbours, with Nuku'alofa as the main study area, and maps where they are active.

## Approaches

| | Approach | Data | Documentation |
|---|---|---|---|
| 1 | Detecting and mapping vessel activity using OBB deep learning (YOLO) | *to be added* | [`docs/approach1-yolo.md`](docs/approach1-yolo.md) *(to be added)* |
| 2 | Statistical anomaly detection + random-forest classification in a PlanetScope time series | PlanetScope 3 m, 2019–2026 | [`docs/approach2-planetscope.md`](docs/approach2-planetscope.md) |

Each approach page describes its workflow, results, how to reproduce it and known gaps.

## Repository layout

```
aoi/                    AOI and analysis-zone polygons (GeoJSON)
docs/
  approach1-yolo.md     Approach 1 workflow (to be added)
  approach2-planetscope.md  Approach 2 workflow, results, reproduction
  decisions.md          method decisions log
  labelling-guide.md    PlanetScope labelling rules and label schema
  scene_selection.xlsx  PlanetScope scene list used for ordering
labels/
  ps_labels.geojson     PlanetScope labels (Approach 2), EPSG:32701
notebooks/
  johan/                Approach 2 notebooks
```

## Licensing and attribution

- **Code:** MIT (see `LICENSE`).
- **Labels and AOIs** (`labels/`, `aoi/`): CC BY 4.0. Labels were made by visual interpretation of satellite imagery and contain point locations, scores and classes only — no image values.
- **PlanetScope imagery** © Planet Labs PBC, used under Planet's Education and Research programme. Imagery and datasets containing image values are not redistributed here; figures in the notebooks are rendered images only.
- **Maxar imagery** used for comparison figures: Maxar Open Data Program, CC BY-NC 4.0. Not included in the repository.
- **Water mask:** ESA WorldCover 10 m 2021 v200, © ESA WorldCover project, CC BY 4.0.