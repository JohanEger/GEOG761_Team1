# Decisions log

Method decisions per approach, and why.

# Approach 2: PlanetScope

Values are the ones used in the notebooks in `notebooks/johan/`. Workflow: [`approach2-planetscope.md`](approach2-planetscope.md).

## Data and study area

| Decision | Rationale |
| --- | --- |
| Study area limited to Nuku'alofa harbour (`aoi/Nukualofa_wharf.geojson`) | Densest vessel activity and daily PlanetScope coverage; Maxar reference imagery exists for Jan 2022. The other harbours planned at the start (Neiafu, Ha'apai, 'Eua) were dropped to stay within quota and time. |
| CRS: EPSG:32701 (WGS 84 / UTM 1S) for all analysis | The study area lies entirely in UTM zone 1S and it is the native CRS of the Maxar tiles. Replaces the earlier choice of EPSG:5887, which was only needed for an archipelago-wide study. |
| Product: PlanetScope 4-band surface reflectance + UDM2, clipped to the AOI, delivered straight to Earth Engine | 4-band is available across Dove Classic, Dove-R and SuperDove, so the 2019–2026 series is consistent. No downloads needed for processing. |
| 29 scenes (2019–2026) from the team scene sheet → 27 acquisitions | Split passes (same date and satellite) are mosaicked into one acquisition. |
| GEE tier: Community | 150 EECU-hours, no billing account needed; the AOI is small enough that compute is not the constraint. |

## Candidate detection

| Decision | Rationale |
| --- | --- |
| Cloud mask: UDM2 cloud, shadow and heavy haze, buffered 30 m; light haze kept | Cloud edges cause false blobs; light haze is common and dropping it loses too many scenes. |
| Drop acquisitions with < 30 % clear water | Too little clear water to normalise the scene reliably. |
| Detection area: WorldCover water + 20 m buffer, restricted to the analysis zone and to pixels with ≥ 5 clear background dates | The buffer keeps boats at the wharves; the zone excludes reef flats and surf; too few clear dates give an unreliable background. |
| Maxar-date acquisitions (14 and 18 Jan 2022) excluded from the background | Kept independent for the Maxar comparison. 18 Jan (`20220118_1026`) is also excluded from labelling and training. |
| Background = 25th percentile of scene-normalised NIR | Transient objects only make pixels brighter; a low percentile stays near clean water and lets boats docked on up to ~75 % of dates still stand out. |
| Noise = IQR / 1.349, smoothed (10 m), floored at the median water noise, capped at 3× | Robust to occasional boats in the stack; the floor and cap stop very quiet or very restless pixels from dominating. |
| Score centred and scaled per scene | Rough or glinty scenes get a stricter effective threshold. |
| Score band: NIR | Water is dark in NIR, so hulls stand out more than in the visible bands. |
| Export threshold score ≥ 6, blobs ≤ 150 px | Deliberately loose (high recall); the classifier filters afterwards. Larger blobs are glint or cloud remnants. |
| Labelling cut-offs: score ≥ 8 harbour, ≥ 12 open water | Keeps the number of candidates to label manageable; open water is choppier. |
| Evaluation and map use one candidate per local score maximum (5×5 px), not per blob centre | Blob centroids of large merged blobs fall far from the boat. |

## Labelling and evaluation

| Decision | Rationale |
| --- | --- |
| All labelling done by one person (JE) | Consistency; no inter-annotator agreement was measured. |
| Test acquisitions: `20190808_1014`, `20211129_2430`, `20260607_2575`, labelled exhaustively | Measures recall of the whole chain, including boats the detector never flagged. Never used for training or tuning. |
| Match tolerance 6 m (2 px), one-to-one | Allows for the candidate sitting a pixel off the label. |

## Classifier

| Decision | Rationale |
| --- | --- |
| Random forest (500 trees, `min_samples_leaf=2`, balanced class weights) | Works well on a few hundred tabular samples; interpretable via permutation importance. |
| Cross-validation grouped by acquisition | Candidates in the same scene share lighting, haze and sensor; random splits would inflate the score. |
| Positive class = `vessel`, `vessel_uncertain`, `wake` | Uncertain boats and wakes still indicate vessel activity. |
| Location features (`dist_land`, `is_harbour`) dropped (variant C) | Avoids the model learning where boats usually are instead of what they look like; also gave the best test recall (12/24 vs 10/24 for variant A). |
| Train on detector candidates only, not manually added boats | The classifier only ever sees candidates in use. |
| Threshold = best-F1 threshold from grouped CV (0.40) | Balances precision and recall; the threshold for ≥ 0.90 recall (0.24) is recorded as an alternative. |