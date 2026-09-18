# Tonga-Vessels

Detection and mapping of small-vessel activity in Tongan waters from PlanetScope imagery.

## What this project does

We use multi-month PlanetScope time series to detect small vessels around the Tongan archipelago and aggregate the detections into activity heat maps. The motivation is humanitarian: when cyclones, tsunamis or volcanic activity damage primary ports, small vessels become an important means of delivering aid, and there is little systematic knowledge of where they operate.

Because PlanetScope pixels are 3 m, the smallest boats are not detectable. Establishing the minimum detectable vessel size is one of the project's research questions, not a limitation to be hidden.

## Pipeline

1. Order and download PlanetScope scenes (`src/ordering.py`)
2. Cloud mask, land mask, tile, check co-registration (`src/preprocess.py`)
3. Find candidate vessels via temporal median background subtraction — in Earth Engine (`src/candidates.py`)
4. Classify candidates as vessel / wake / false positive — in Colab (`src/classify.py`)
5. Aggregate to a grid and produce heat maps (`src/aggregate.py`)

Imagery never touches anyone's disk or Drive. Steps 2 and 3 run server-side on the delivered collection; only candidate points and small patches are exported.

## Getting started

1. Ask to be added as a collaborator on this repo.
2. Ask to be added to the Google Cloud project groupprojectgeog761 so you can read the Earth Engine collection, and as a member of the tonga-vessels-data Shared Drive. A Shared Drive appears automatically once you are a member — no shortcut needed, and the path is the same for everyone.
3. Read the workflow guide before your first session.
4. Open a notebook in Colab and run `notebooks/shared/00_setup_check.ipynb`. If every cell completes, you are set up. The last two cells show the standard header and the save-your-work cell — copy both into every notebook you make.

You do not need to install anything locally. Colab is enough.

## Repository layout

```
aoi/          study area polygons (GeoJSON)
src/          shared, reusable code — import this from notebooks
              (gee.py holds Earth Engine session setup and export helpers)
notebooks/    one folder per person; shared/ changes only via pull request
labels/       annotation files (GeoJSON) — small enough for Git
docs/         workflow guide, labelling guide, decisions log
```
Imagery is **not** stored in this repo, and not in Drive either — it lives in the project's Earth Engine ImageCollection. The shared Drive folder holds only exported patches, labels, models and outputs.

**IMPORTANT**
Earth Engine exports go to the personal Drive of whoever runs the task — it cannot write to a Shared Drive directly — so move exported files across afterwards.


## Conventions

- Branch names: `<yourname>/<task>`, short-lived, merged within a few days
- Never commit directly to `main`
- Parameters and paths come from `config.yaml`, never hardcoded in notebooks
- Run the nbstripout line in the save cell before committing, so outputs stay out of Git
- CRS is EPSG:5887 (Tonga Map Grid) everywhere — Tonga straddles the UTM 1S/2S boundary
- Check quota before ordering; GEE deliveries count against the monthly allowance
- File naming: `<aoi>_<YYYYMMDD>_<product>_<processing>.tif`
- Decisions go in `docs/decisions.md` with a date

## Data licensing

PlanetScope imagery is licensed to us under Planet's Education and Research programme.
Do not redistribute imagery or any derived product that could reconstruct it. Check the
licence terms before publishing figures or releasing label files.
