# Areas of interest

GeoJSON polygons, WGS84 (EPSG:4326), one file per area. Draw them in QGIS or
geojson.io and keep them simple — a few vertices is enough.

Expected files:

- `tonga_full.geojson` — full study area
- `nukualofa.geojson` — Nuku'alofa harbour, Tongatapu (overlaps Maxar Open Data)
- `neiafu.geojson` — Neiafu harbour, Vava'u
- `pangai.geojson` — Pangai, Ha'apai

Include enough water around each harbour to capture approaches and anchorages, but
clip tightly enough that orders do not waste quota on open ocean.
