"""Search Planet's catalogue for PlanetScope scenes over an AOI and write a shortlist CSV.

Uses ONLY the Data API search endpoints. Searching returns metadata, not pixels, so it
does NOT consume download quota. Nothing here orders, activates or downloads imagery.

Usage (from the repo root):

    export PL_API_KEY=...            # or put it in Colab Secrets as PL_API_KEY
    python scripts/search_scenes.py aoi/nukualofa.geojson --start 2022-01-01 --end 2022-12-31
    python scripts/search_scenes.py aoi/eua.geojson --start 2024-01-01 --end 2024-12-31 --aoi-clear

Output: docs/scene_candidates_<aoi>.csv, one row per scene, sorted by date, with empty
review columns (glint, reviewer, keep, notes) for the team to fill in after a visual check.

--aoi-clear asks Planet how clear each scene is *within the AOI* (not the whole scene),
using the item coverage endpoint. One extra request per scene, still no quota. If the
endpoint is unavailable for your account the column is left blank and the script carries on.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform

API = "https://api.planet.com/data/v1"
TONGA_TZ = timezone(timedelta(hours=13))
TO_M = Transformer.from_crs(4326, 5887, always_xy=True).transform   # Tonga Map Grid, metres


def api_key() -> str:
    key = os.environ.get("PL_API_KEY")
    if not key:
        try:
            from google.colab import userdata          # running in Colab
            key = userdata.get("PL_API_KEY")
        except Exception:
            pass
    if not key:
        sys.exit("No API key. Set PL_API_KEY in the environment or in Colab Secrets.")
    return key


def load_geometry(path: Path) -> dict:
    gj = json.loads(path.read_text())
    if gj.get("type") == "FeatureCollection":
        if len(gj["features"]) != 1:
            sys.exit(f"{path} holds {len(gj['features'])} features; expected exactly one.")
        return gj["features"][0]["geometry"]
    return gj.get("geometry", gj)


def search(session: requests.Session, geom: dict, start: str, end: str,
           max_cloud: float, item_type: str, asset: str) -> list[dict]:
    """Quick-search with pagination. Returns raw feature dicts."""
    body = {
        "item_types": [item_type],
        "filter": {
            "type": "AndFilter",
            "config": [
                {"type": "GeometryFilter", "field_name": "geometry", "config": geom},
                {"type": "DateRangeFilter", "field_name": "acquired",
                 "config": {"gte": f"{start}T00:00:00Z", "lte": f"{end}T23:59:59Z"}},
                {"type": "RangeFilter", "field_name": "cloud_cover",
                 "config": {"lte": max_cloud}},
                {"type": "AssetFilter", "config": [asset]},   # only scenes with this bundle
            ],
        },
    }
    r = session.post(f"{API}/quick-search?_page_size=250", json=body)
    r.raise_for_status()
    page = r.json()
    items = list(page["features"])
    while page["_links"].get("_next"):
        r = session.get(page["_links"]["_next"])
        r.raise_for_status()
        page = r.json()
        items.extend(page["features"])
    return items


def aoi_clear_percent(session: requests.Session, item_type: str, item_id: str,
                      geom: dict) -> float | None:
    """Clear percentage within the AOI, from Planet's item coverage endpoint.

    Returns None if the endpoint is unavailable or the estimate is not ready.
    """
    url = f"{API}/item-types/{item_type}/items/{item_id}/coverage"
    for _ in range(3):
        try:
            r = session.post(url, json={"geometry": geom})
        except requests.RequestException:
            return None
        if r.status_code == 429:                 # rate limited — back off and retry
            time.sleep(2)
            continue
        if not r.ok:
            return None
        data = r.json()
        if data.get("status") == "complete":
            return data.get("clear_percent")
        time.sleep(1)                            # still computing
    return None


def row_for(item: dict, aoi_m, aoi_name: str) -> dict:
    p = item["properties"]
    footprint_m = transform(TO_M, shape(item["geometry"]))
    overlap_km2 = footprint_m.intersection(aoi_m).area / 1e6
    acquired = datetime.fromisoformat(p["acquired"].replace("Z", "+00:00"))
    return {
        "aoi": aoi_name,
        "item_id": item["id"],
        "acquired_utc": acquired.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acquired_tonga": acquired.astimezone(TONGA_TZ).strftime("%Y-%m-%d %H:%M"),
        "weekday": acquired.astimezone(TONGA_TZ).strftime("%a"),
        "instrument": p.get("instrument"),
        "satellite_id": p.get("satellite_id"),
        "cloud_cover_scene": round(p.get("cloud_cover", 0) * 100, 1),
        "clear_percent_scene": p.get("clear_percent"),
        "clear_percent_aoi": "",
        "aoi_coverage_pct": round(100 * overlap_km2 / (aoi_m.area / 1e6), 1),
        "est_quota_km2": round(overlap_km2, 1),
        "view_angle": round(p.get("view_angle", 0), 1),
        "sun_elevation": round(p.get("sun_elevation", 0), 1),
        "quality": p.get("quality_category"),
        "glint": "",
        "reviewer": "",
        "keep": "",
        "notes": "",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("aoi", type=Path, help="AOI GeoJSON, e.g. aoi/nukualofa.geojson")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--max-cloud", type=float, default=0.5,
                    help="scene-level cloud cover ceiling, 0-1 (default 0.5 — the AOI "
                         "may be clear even when the scene is not)")
    ap.add_argument("--min-coverage", type=float, default=90,
                    help="drop scenes covering less than this %% of the AOI (default 90)")
    ap.add_argument("--instrument", default=None,
                    help="keep only this instrument, e.g. PSB.SD for SuperDove 8-band")
    ap.add_argument("--asset", default="ortho_analytic_8b_sr",
                    help="required asset (default ortho_analytic_8b_sr)")
    ap.add_argument("--aoi-clear", action="store_true",
                    help="also fetch clear %% within the AOI (one request per scene)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    aoi_name = args.aoi.stem
    geom = load_geometry(args.aoi)
    aoi_m = transform(TO_M, shape(geom))
    out = args.out or Path("docs") / f"scene_candidates_{aoi_name}.csv"

    session = requests.Session()
    session.auth = (api_key(), "")

    print(f"Searching {aoi_name} ({aoi_m.area/1e6:.1f} km²), {args.start} to {args.end} ...")
    items = search(session, geom, args.start, args.end,
                   args.max_cloud, "PSScene", args.asset)
    print(f"  {len(items)} scenes returned by Planet")

    rows = [row_for(it, aoi_m, aoi_name) for it in items]
    rows = [r for r in rows if r["aoi_coverage_pct"] >= args.min_coverage]
    if args.instrument:
        rows = [r for r in rows if r["instrument"] == args.instrument]
    print(f"  {len(rows)} after coverage >= {args.min_coverage}%"
          + (f" and instrument = {args.instrument}" if args.instrument else ""))

    if args.aoi_clear and rows:
        print("  fetching clear % within the AOI ...")
        for i, r in enumerate(rows, 1):
            v = aoi_clear_percent(session, "PSScene", r["item_id"], geom)
            r["clear_percent_aoi"] = "" if v is None else v
            if i % 25 == 0:
                print(f"    {i}/{len(rows)}")

    rows.sort(key=lambda r: r["acquired_utc"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    total = sum(r["est_quota_km2"] for r in rows)
    print(f"Wrote {len(rows)} rows to {out}")
    print(f"If you ordered ALL of them, clipped: ~{total:,.0f} km² of quota. "
          f"Pick the best ones before ordering.")


if __name__ == "__main__":
    main()