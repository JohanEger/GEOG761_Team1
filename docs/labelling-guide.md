# Labelling guide

Rules used to label PlanetScope candidates in QGIS. The resulting layer is `labels/ps_labels_60_percent_labelled.geojson`.

## What was labelled

| Purpose | Acquisitions | How |
|---|---|---|
| **Training** | all acquisitions except test and `20220118_1026` | Candidates from `candidate_detection.ipynb` above the labelling cut-offs (score ≥ 8 harbour, ≥ 12 open water) were given a class. Obvious boats the detector missed were added as manual points. |
| **Test** | `20190808_1014`, `20211129_2430`, `20260607_2575` | Every visible vessel labelled as a manual point, so recall of the whole pipeline can be measured. |
| **Maxar evaluation** | `20220114_2223` | Labelled like training, kept separate (`set = maxar_eval`). |

## Display in QGIS

- Product is 4-band surface reflectance: band 1 Blue, 2 Green, 3 Red, 4 NIR.
- True colour: R = 3, G = 2, B = 1, cumulative count cut 2–98 %.
- NIR: single-band grey on band 4. Boats are usually bright against dark water in NIR and often easier to see than in RGB.
- No-data value 0 → transparent. Use the same stretch on every scene so brightness is comparable between dates.

## Classes

- **vessel** — confident this is a boat
- **vessel_uncertain** — probably a boat, but not confirmable
- **wake** — a wake is visible; the hull itself may be indistinct
- **false_positive** — whitecap, cloud edge or shadow, reef break, wharf edge, rock, buoy, sun glint

## How to judge a candidate

1. Look at the scene in RGB **and** NIR.
2. Compare with one or two neighbouring dates. Present on this date only, over water → likely vessel. Present on all dates → fixed feature.
3. Elongated bright blob with a linear trail → vessel, with the wake labelled separately as `wake`.
4. Bright, irregular, many small specks in a band → whitecaps → `false_positive`.
5. Near a cloud edge or shadow → `vessel_uncertain` at most.

When unsure, label with `confidence = low` rather than skipping. One point per blob, at its centre. Packed boats appearing as one blob = one point with `n_hulls` > 1.

For test scenes, label exhaustively with the candidate layer hidden, so the labels are not anchored on what the detector found.

## Fields in `ps_labels`

| Field | Meaning |
|---|---|
| `acq_id` | acquisition ID (`YYYYMMDD_<satellite>`) |
| `scene_ids` | PlanetScope scene ID(s) in the acquisition |
| `date` | acquisition time (UTC) |
| `zone` | `harbour`, `open` or `shore`, from `aoi/analysis_zone.geojson` |
| `score_max`, `area_px` | detector peak score and blob size (candidates only) |
| `class` | vessel, vessel_uncertain, wake, false_positive; empty = not labelled |
| `confidence` | high, low |
| `n_hulls`, `length_m` | estimated number of boats in the blob; length for elongated blobs |
| `source` | `candidate` (from the detector) or `manual` (added by hand) |
| `set` | `train`, `test`, `maxar_eval` |
| `labeller` | initials |
| `notes` | free text |

`max` and `count` duplicate `score_max` and `area_px`; `blob`, `id` and `fid` are internal IDs from the export.

## Matching labels to detections

Labels and candidates are matched one-to-one within 6 m (2 pixels):
- labelled vessel with a matching candidate → detected
- labelled vessel without one → missed by the detector
- candidate without a label → false positive, or a boat the labeller missed