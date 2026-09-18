# Labelling guide

Draft. Revise after the first calibration round and record changes here.

**NOTE!**: This is a suggestion from Claude. Team needs to agree on this.

## What we are labelling

Candidate patches produced by `src/candidates.py`, not raw scenes. Each candidate is a
bright anomaly over water. Your job is to judge what it is.

## Classes

- **vessel** — confident this is a boat
- **vessel_uncertain** — probably a boat, but not confirmable
- **wake** — a wake is visible; the hull itself may be indistinct
- **false_positive** — whitecap, cloud edge or shadow, reef break, rock, buoy, sun glint

## How to judge

Always label with the temporal median background and at least two neighbouring dates on
screen. A feature present across many dates is not a boat. A feature present on one date
only, over water, usually is.

Where high-resolution reference imagery exists (Maxar for Nuku'alofa, January 2022;
Google Earth or Esri Wayback elsewhere), use it to identify permanent features. Add
those to the harbour's exclusion list so nobody labels them again.

## Rules to agree in the first calibration round

- How to handle a cluster of moored boats: one label or several?
- Minimum confidence for `vessel` rather than `vessel_uncertain`
- Whether a wake with no visible hull counts as a detection
- How to treat objects partly under cloud

## Calibration

Everyone labels the same 50-100 patches before real annotation starts. Compare, discuss
disagreements, revise this guide. Repeat if agreement is poor. Record the agreement
figure — it goes in the write-up.

## What gets stored

GeoJSON with: coordinates, timestamp, scene ID, class, annotator, confidence.
Never only the class — provenance matters when we revisit labels later.
