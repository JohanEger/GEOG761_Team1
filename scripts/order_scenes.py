"""Check, order and log PlanetScope scenes for one AOI, without wasting quota.

Run from the repo root, locally or in Colab (`!python scripts/...`). Commands that talk
to Planet need the API key in PL_API_KEY (environment variable or Colab Secrets).

    # 1. Check the scene IDs. Nothing is ordered and no quota is used.
    python scripts/order_scenes.py check --aoi aoi/Nukualofa_wharf.geojson --ids-from scene_selection.xlsx

    # 2. Build the order and print it (dry run), then place it with --submit.
    #    Start with ONE scene: it shows that delivery works and what a clipped scene costs.
    python scripts/order_scenes.py order --aoi aoi/Nukualofa_wharf.geojson --ids 20250110_220650_09_24dd
    python scripts/order_scenes.py order --aoi aoi/Nukualofa_wharf.geojson --ids 20250110_220650_09_24dd --submit

    # 3. Refresh order states in the logs.
    python scripts/order_scenes.py status

    # Ordered in Planet's web app instead? Log it.
    python scripts/order_scenes.py record <order_id> --aoi aoi/Nukualofa_wharf.geojson

--ids-from takes the scene sheet as .xlsx or .csv (column scene_id or item_id; if the
sheet has an aoi column, only rows for --aoi are used) or a .txt with one ID per line.
`check --offline` checks the ID format and the ledger without an API key.

Placed orders are logged at once in docs/ordered_scenes.csv (one row per scene) and
docs/data_catalogue.csv (one row per order). Commit and push both, so the rest of the
team can see what has been ordered.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import ordering            # noqa: E402
from src.config import load_config  # noqa: E402

ID_COLUMNS = ("scene_id", "item_id", "id")
CHECK_COLUMNS = ["item_id", "status", "instrument", "acquired_utc", "cloud_cover",
                 "aoi_coverage_pct", "est_km2", "note"]


# --------------------------------------------------------------------------
# Input and output
# --------------------------------------------------------------------------

def read_ids(path: Path, aoi_name: str) -> list[str]:
    """Scene IDs from a .txt, .csv or .xlsx file, keeping only rows for this AOI."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        lines = [s.strip() for s in path.read_text(encoding="utf-8").splitlines()]
        return [s for s in lines if s and not s.startswith("#")]
    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
    elif suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            sys.exit("Reading .xlsx needs openpyxl (pip install openpyxl), "
                     "or export the sheet as CSV.")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            table = [["" if v is None else str(v) for v in row]
                     for row in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    else:
        sys.exit(f"Cannot read {path.name}: use .txt, .csv or .xlsx")

    table = [row for row in table if any(cell.strip() for cell in row)]
    if not table:
        return []
    header = [h.strip().lower() for h in table[0]]
    id_col = next((header.index(c) for c in ID_COLUMNS if c in header), None)
    if id_col is None:
        sys.exit(f"{path.name}: no column named {' / '.join(ID_COLUMNS)}")
    aoi_col = header.index("aoi") if "aoi" in header else None

    ids = []
    for row in table[1:]:
        cell = row[id_col].strip() if id_col < len(row) else ""
        aoi = row[aoi_col].strip() if aoi_col is not None and aoi_col < len(row) else ""
        if cell and (not aoi or Path(aoi).stem.lower() == aoi_name.lower()):
            ids.append(cell)
    return ids


def collect_ids(args, aoi_name: str) -> list[str]:
    """IDs from --ids and --ids-from, duplicates dropped with a warning."""
    ids = list(args.ids)
    if args.ids_from:
        ids += read_ids(args.ids_from, aoi_name)
    unique = list(dict.fromkeys(ids))
    if len(unique) < len(ids):
        print(f"Note: dropped {len(ids) - len(unique)} duplicate ID(s).")
    return unique


def print_table(rows: list[dict], columns: list[str]) -> None:
    widths = {c: max([len(c)] + [len(str(r.get(c, ""))) for r in rows]) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns).rstrip())
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns).rstrip())


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def default_name() -> str:
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True,
                              text=True, cwd=REPO_ROOT).stdout.strip()
    except OSError:
        return ""


# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------

def offline_row(item_id: str, bundle: str) -> dict:
    """What can be said about a scene from its ID alone."""
    parsed = ordering.parse_item_id(item_id)
    row = {"item_id": item_id, "status": "format_ok", "note": ""}
    if parsed is None:
        row.update(status="bad_format", note="not a PSScene ID pattern: check for a typo")
    else:
        row["acquired_utc"] = parsed["acquired_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if parsed["dove_classic"]:
            row["instrument"] = "PS2"
            if "8b" in bundle:
                row.update(status="no_bundle", note="Dove Classic: 4-band only")
    return row


def checked_rows(args, cfg, aoi_name: str, aoi: dict, ids: list[str], bundle: str,
                 session=None) -> tuple[list[dict], dict]:
    """Check rows for each ID, with ledger hits marked. Returns (rows, other-AOI hits)."""
    if getattr(args, "offline", False):
        rows = [offline_row(i, bundle) for i in ids]
    else:
        rows = ordering.check_items(session or ordering.planet_session(), ids, aoi,
                                    bundle, cfg["planet"]["item_type"], cfg["crs"])
    same, other = ordering.ledger_conflicts(ids, aoi_name, args.ledger)
    for r in rows:
        r.setdefault("note", "")
        if r["item_id"] in same and not getattr(args, "allow_reorder", False):
            hit = same[r["item_id"]]
            r.update(status="already_ordered",
                     note=f"order {hit['order_id']} by {hit['ordered_by']} ({hit['state']})")
        elif r["item_id"] in other:
            aois = sorted({h["aoi"] for h in other[r["item_id"]]})
            r["note"] = (r["note"] + "; " if r["note"] else "") + \
                "also ordered for " + ", ".join(aois)
    return rows, other


def summarise(rows: list[dict], aoi_km2: float, cfg: dict) -> float:
    """Print counts and the quota estimate; return the estimate in km²."""
    ok = [r for r in rows if r["status"] in ("ok", "format_ok")]
    problems = {}
    for r in rows:
        if r not in ok:
            problems[r["status"]] = problems.get(r["status"], 0) + 1
    exact = all(r.get("est_km2") not in ("", None) for r in ok)
    est = (sum(float(r["est_km2"]) for r in ok) if exact else len(ok) * aoi_km2)
    budget = cfg.get("quota", {}).get("monthly_km2")
    print(f"\nOrderable: {len(ok)} of {len(rows)}"
          + (" | problems: " + ", ".join(f"{k} {v}" for k, v in sorted(problems.items()))
             if problems else ""))
    print(f"Quota if ordered, clipped to the AOI: {'' if exact else 'at most '}"
          f"{est:,.1f} km2"
          + (f" ({100 * est / budget:.0f}% of the {budget:,} km2/month in config.yaml)"
             if budget else ""))
    print("That assumes Planet charges the clipped area (config quota.charged_on is still "
          "TBD). Charged per full scene, it would be several hundred km2 per scene.")
    return est


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_check(args, cfg) -> int:
    aoi_name, aoi = ordering.load_aoi_file(args.aoi)
    ids = collect_ids(args, aoi_name)
    if not ids:
        sys.exit("No scene IDs given (use --ids and/or --ids-from).")
    bundle = args.bundle or cfg["planet"]["asset"]
    aoi_km2 = ordering.area_km2(aoi, cfg["crs"])
    print(f"AOI {aoi_name}: {aoi_km2:.1f} km2 | bundle {bundle} | {len(ids)} scene IDs"
          + (" | offline: ID format and ledger only" if args.offline else ""))
    rows, _ = checked_rows(args, cfg, aoi_name, aoi, ids, bundle)
    print()
    print_table(rows, CHECK_COLUMNS)
    summarise(rows, aoi_km2, cfg)
    if args.out:
        write_csv(args.out, rows, CHECK_COLUMNS)
        print(f"Wrote {args.out}")
    return 0


def cmd_order(args, cfg) -> int:
    aoi_name, aoi = ordering.load_aoi_file(args.aoi)
    ids = collect_ids(args, aoi_name)
    if not ids:
        sys.exit("No scene IDs given (use --ids and/or --ids-from).")
    bundle = cfg["planet"]["asset"]
    session = ordering.planet_session()
    rows, other = checked_rows(args, cfg, aoi_name, aoi, ids, bundle, session)
    print_table(rows, CHECK_COLUMNS)

    bad = [r for r in rows if r["status"] != "ok"]
    if bad and not args.skip_problems:
        print(f"\n{len(bad)} scene(s) cannot be ordered as {bundle} for {aoi_name}. "
              "Remove them, or pass --skip-problems to order the rest.")
        return 1
    good = [r for r in rows if r["status"] == "ok"]
    if not good:
        print("\nNothing to order.")
        return 1

    est = {r["item_id"]: float(r["est_km2"]) for r in good}
    total = summarise(good, ordering.area_km2(aoi, cfg["crs"]), cfg)
    if other:
        print("Some scenes are already ordered for another AOI: the overlap is charged again.")
    name = args.name or f"{aoi_name}_{datetime.now(timezone.utc):%Y%m%d}_{len(good)}scenes"
    request = ordering.build_order(list(est), aoi, cfg, name)

    if not args.submit:
        print(f"\nOrder request '{name}':")
        print(json.dumps(request, indent=2))
        print("\nDry run: nothing was ordered. Add --submit to place this order.")
        return 0

    budget = cfg.get("quota", {}).get("monthly_km2")
    if budget and total > budget and not args.force:
        print(f"\nEstimated {total:,.0f} km2 is more than the monthly allowance "
              f"({budget:,} km2). Split the order, or pass --force.")
        return 1
    ledger_rows = ordering.read_rows(args.ledger or ordering.LEDGER)
    if len(good) > 1 and not any(r.get("state") == "success" for r in ledger_rows) \
            and not args.skip_test_order:
        print("\nNo logged order has succeeded yet. Place a ONE-scene test order first: "
              "it shows that delivery works and what a clipped scene really costs "
              "(compare your quota before and after). Or pass --skip-test-order.")
        return 1
    by = args.by or default_name()
    if not by:
        sys.exit("Pass --by <your name> so the ledger shows who ordered.")

    order_id = ordering.place_order(request, aoi_name=aoi_name, ordered_by=by,
                                    est_km2=est, session=session, ledger=args.ledger,
                                    catalogue=args.catalogue,
                                    allow_reorder=args.allow_reorder)
    print(f"\nOrder placed: {order_id}")
    print("Logged in docs/ordered_scenes.csv and docs/data_catalogue.csv: commit and push "
          "both. Then follow the order with:  python scripts/order_scenes.py status")
    return 0


def cmd_status(args, cfg) -> int:
    if not args.offline:
        for order_id, old, new in ordering.refresh_ledger(ledger=args.ledger,
                                                          catalogue=args.catalogue):
            print(f"{order_id}: {old} -> {new}")
    rows = ordering.read_rows(args.ledger or ordering.LEDGER)
    if not rows:
        print("No orders logged yet.")
        return 0

    orders = {}
    for r in rows:
        o = orders.setdefault(r["order_id"], {
            "order_id": r["order_id"], "aoi": r["aoi"], "scenes": 0, "est_km2": 0.0,
            "state": r["state"], "ordered_by": r["ordered_by"],
            "ordered_at_utc": r["ordered_at_utc"][:16]})
        o["scenes"] += 1
        o["est_km2"] += float(r["est_km2"] or 0)
    table = sorted(orders.values(), key=lambda o: o["ordered_at_utc"])
    for o in table:
        o["est_km2"] = round(o["est_km2"], 1)
    print_table(table, ["order_id", "aoi", "scenes", "est_km2", "state", "ordered_by",
                        "ordered_at_utc"])

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    used = {}
    for o in table:
        if o["ordered_at_utc"].startswith(month) and \
                o["state"] not in ordering.REORDERABLE_STATES:
            used[o["ordered_by"]] = used.get(o["ordered_by"], 0) + o["est_km2"]
    if used:
        print(f"\nEstimated quota used in {month} (UTC): "
              + ", ".join(f"{who} {km2:,.1f} km2" for who, km2 in sorted(used.items())))
    return 0


def cmd_record(args, cfg) -> int:
    aoi_name, aoi = ordering.load_aoi_file(args.aoi)
    by = args.by or default_name()
    if not by:
        sys.exit("Pass --by <your name> so the ledger shows who ordered.")
    order = ordering.record_order(args.order_id, aoi_name=aoi_name, ordered_by=by,
                                  aoi_geojson=aoi, ledger=args.ledger,
                                  catalogue=args.catalogue, crs=cfg["crs"])
    n = sum(len(p["item_ids"]) for p in order.get("products", []))
    print(f"Logged order {args.order_id} ({n} scenes, state {order.get('state')}). "
          "Commit and push docs/ordered_scenes.csv and docs/data_catalogue.csv.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def scene_args(p):
        p.add_argument("--aoi", required=True, type=Path,
                       help="AOI GeoJSON, e.g. aoi/Nukualofa_wharf.geojson")
        p.add_argument("--ids", nargs="+", default=[], metavar="ID", help="scene IDs")
        p.add_argument("--ids-from", type=Path,
                       help="scene sheet (.xlsx/.csv) or ID list (.txt)")

    p = sub.add_parser("check", help="check scene IDs; orders nothing, uses no quota")
    scene_args(p)
    p.add_argument("--bundle", help="product bundle (default: planet.asset in config.yaml)")
    p.add_argument("--offline", action="store_true",
                   help="ID format and ledger only; no API key needed")
    p.add_argument("--out", type=Path, help="also write the table to this CSV")

    p = sub.add_parser("order", help="build an order (dry run); place it with --submit")
    scene_args(p)
    p.add_argument("--name", help="order name (default <aoi>_<date>_<n>scenes)")
    p.add_argument("--by", help="who is ordering (default: git user.name)")
    p.add_argument("--submit", action="store_true", help="place the order")
    p.add_argument("--skip-problems", action="store_true",
                   help="order the scenes that pass the check and drop the rest")
    p.add_argument("--allow-reorder", action="store_true",
                   help="order scenes the ledger already holds for this AOI")
    p.add_argument("--skip-test-order", action="store_true",
                   help="allow a multi-scene order before any order has succeeded")
    p.add_argument("--force", action="store_true",
                   help="allow an order estimated above the monthly allowance")

    p = sub.add_parser("status", help="refresh order states and show the ledger")
    p.add_argument("--offline", action="store_true", help="show the ledger only")

    p = sub.add_parser("record", help="log an order placed in Planet's web app")
    p.add_argument("order_id")
    p.add_argument("--aoi", required=True, type=Path,
                   help="the AOI the order was clipped to")
    p.add_argument("--by", help="who ordered it (default: git user.name)")

    for p in sub.choices.values():          # for tests and dry experiments
        p.add_argument("--ledger", type=Path, default=None, help=argparse.SUPPRESS)
        p.add_argument("--catalogue", type=Path, default=None, help=argparse.SUPPRESS)
        p.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    commands = {"check": cmd_check, "order": cmd_order, "status": cmd_status,
                "record": cmd_record}
    return commands[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
