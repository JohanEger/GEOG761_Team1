# Areas of interest

| File | Used for |
|---|---|
| `Nukualofa_wharf.geojson` | Ordering clip AOI for all PlanetScope scenes; outline in the maps. |
| `analysis_zone.geojson` | Polygons with a `zone` field (`harbour`, `open`, `shore`) drawn in QGIS. Restricts detection to the harbour, wharf basins and approaches (reef flats and surf excluded), and assigns each candidate a zone. |

The notebooks reproject both files on load, so any CRS works.