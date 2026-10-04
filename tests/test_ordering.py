"""Offline tests for src/ordering.py and scripts/order_scenes.py.

No API key needed and no quota used: a fake session stands in for Planet.
Run from the repo root:  python -m pytest tests -q
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import ordering            # noqa: E402
from src.config import load_config  # noqa: E402

WHARF_FILE = ROOT / "aoi" / "Nukualofa_wharf.geojson"
AOI_NAME, AOI = ordering.load_aoi_file(WHARF_FILE)
CFG = load_config()

SUPERDOVE = "20250110_220650_09_24dd"
DOVE_R = "20210722_222152_01_1065"
DOVE_CLASSIC = "20190623_213507_1054"
MALFORMED = "20220405_212626_1_1005"
OTHER_SUPERDOVE = "20240101_220000_00_2400"


def box(west, south, east, north):
    return {"type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north],
                             [west, north], [west, south]]]}


COVERS_AOI = box(-175.30, -21.25, -175.05, -20.95)
WEST_PART = box(-175.30, -21.25, -175.19, -20.95)
VAVAU = box(-174.10, -18.80, -173.90, -18.60)

PERMS_8B = ["assets.ortho_analytic_8b_sr:download", "assets.ortho_analytic_4b_sr:download",
            "assets.ortho_udm2:download"]
PERMS_4B = ["assets.ortho_analytic_4b_sr:download", "assets.ortho_udm2:download"]


def item(item_id, geometry=COVERS_AOI, perms=PERMS_8B, instrument="PSB.SD"):
    return {"id": item_id, "type": "Feature", "geometry": geometry, "_permissions": perms,
            "properties": {"instrument": instrument, "acquired": "2025-01-10T22:06:50Z",
                           "cloud_cover": 0.02}}


def item_url(item_id):
    return f"{ordering.DATA_API}/item-types/PSScene/items/{item_id}"


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakePlanet:
    """Replays canned responses per (method, url); the last one keeps repeating."""

    def __init__(self, routes=None):
        self.routes = {k: list(v) for k, v in (routes or {}).items()}
        self.calls = []

    def add(self, method, url, *responses):
        self.routes.setdefault((method, url), []).extend(responses)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        queue = self.routes.get((method, url))
        if not queue:
            raise AssertionError(f"unexpected request: {method} {url}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def accepted(request, order_id="order-1"):
    """What the Orders API returns for an accepted order."""
    return FakeResponse(202, {"id": order_id, "name": request["name"], "state": "queued",
                              "created_on": "2026-10-06T01:02:03.456Z",
                              "products": request["products"], "tools": request["tools"],
                              "delivery": request["delivery"]})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(ordering.time, "sleep", lambda seconds: None)


@pytest.fixture
def logs(tmp_path):
    """Empty ledger and catalogue with the repo's real headers."""
    ledger = tmp_path / "ordered_scenes.csv"
    catalogue = tmp_path / "data_catalogue.csv"
    shutil.copy(ROOT / "docs" / "ordered_scenes.csv", ledger)
    shutil.copy(ROOT / "docs" / "data_catalogue.csv", catalogue)
    return ledger, catalogue


def write_ledger(path, rows):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ordering.LEDGER_FIELDS, lineterminator="\n")
        for r in rows:
            w.writerow({**dict.fromkeys(ordering.LEDGER_FIELDS, ""), **r})


def load_cli():
    spec = importlib.util.spec_from_file_location(
        "order_scenes", ROOT / "scripts" / "order_scenes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load_cli()


# --------------------------------------------------------------------------
# IDs and area
# --------------------------------------------------------------------------

def test_parse_item_id():
    sd = ordering.parse_item_id(SUPERDOVE)
    assert sd["acquired_utc"].isoformat() == "2025-01-10T22:06:50+00:00"
    assert sd["satellite_id"] == "24dd" and not sd["dove_classic"]
    assert ordering.parse_item_id(DOVE_CLASSIC)["dove_classic"]
    assert ordering.parse_item_id(MALFORMED) is None
    assert ordering.parse_item_id("20251310_220650_09_24dd") is None     # month 13
    assert ordering.parse_item_id(" " + SUPERDOVE) is None


def test_wharf_area_and_clipping():
    area = ordering.area_km2(AOI)
    assert area == pytest.approx(47.5, abs=0.1)
    assert ordering.estimate_quota(AOI, 30) == pytest.approx(30 * area)

    km2, pct = ordering.clipped_area(COVERS_AOI, AOI)
    assert km2 == pytest.approx(area) and pct == pytest.approx(100)
    km2, pct = ordering.clipped_area(WEST_PART, AOI)
    assert 0 < km2 < area and 0 < pct < 100
    assert ordering.clipped_area(VAVAU, AOI) == (0, 0)


def test_bundle_available():
    assert ordering.bundle_available(item(SUPERDOVE), "analytic_8b_sr_udm2") is True
    dove_r = item(DOVE_R, perms=PERMS_4B)
    assert ordering.bundle_available(dove_r, "analytic_8b_sr_udm2") is False
    assert ordering.bundle_available(dove_r, "analytic_sr_udm2") is True
    assert ordering.bundle_available(item(SUPERDOVE), "made_up_bundle") is None
    listed = {"assets": ["ortho_analytic_8b_sr", "ortho_udm2"]}
    assert ordering.bundle_available(listed, "analytic_8b_sr_udm2") is True
    assert ordering.bundle_available({}, "analytic_8b_sr_udm2") is None


# --------------------------------------------------------------------------
# check_items
# --------------------------------------------------------------------------

def test_check_items_reports_each_problem():
    planet = FakePlanet()
    planet.add("GET", item_url(SUPERDOVE), FakeResponse(200, item(SUPERDOVE)))
    planet.add("GET", item_url(DOVE_R),
               FakeResponse(200, item(DOVE_R, perms=PERMS_4B, instrument="PS2.SD")))
    planet.add("GET", item_url(MALFORMED), FakeResponse(404, {"message": "not found"}))
    far, part = "20240101_220000_00_2400", "20240102_220000_00_2401"
    planet.add("GET", item_url(far), FakeResponse(200, item(far, geometry=VAVAU)))
    planet.add("GET", item_url(part), FakeResponse(429),
               FakeResponse(200, item(part, geometry=WEST_PART)))

    rows = ordering.check_items(planet, [SUPERDOVE, DOVE_R, MALFORMED, far, part], AOI,
                                "analytic_8b_sr_udm2")

    assert {r["item_id"]: r["status"] for r in rows} == {
        SUPERDOVE: "ok", DOVE_R: "no_bundle", MALFORMED: "not_found",
        far: "outside_aoi", part: "ok"}
    by_id = {r["item_id"]: r for r in rows}
    assert by_id[SUPERDOVE]["aoi_coverage_pct"] == 100.0
    assert by_id[SUPERDOVE]["est_km2"] == pytest.approx(47.5, abs=0.1)
    assert 0 < by_id[part]["est_km2"] < by_id[SUPERDOVE]["est_km2"]
    assert sum(url == item_url(part) for _, url, _ in planet.calls) == 2   # retried the 429
    assert all(method == "GET" for method, _, _ in planet.calls)          # nothing ordered


def test_rejected_api_key_is_reported_clearly():
    planet = FakePlanet({("GET", item_url(SUPERDOVE)): [FakeResponse(401)]})
    with pytest.raises(RuntimeError, match="API key"):
        ordering.check_items(planet, [SUPERDOVE], AOI, "analytic_8b_sr_udm2")


# --------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------

def test_ledger_conflicts(logs):
    ledger, _ = logs
    write_ledger(ledger, [
        {"item_id": "A", "aoi": "Nukualofa_wharf", "order_id": "o1", "state": "success"},
        {"item_id": "B", "aoi": "Nukualofa_wharf", "order_id": "o2", "state": "failed"},
        {"item_id": "C", "aoi": "Nukualofa_coast", "order_id": "o3", "state": "queued"},
    ])
    same, other = ordering.ledger_conflicts(["A", "B", "C", "D"], "nukualofa_WHARF", ledger)
    assert set(same) == {"A"}           # B failed, so it may be ordered again
    assert set(other) == {"C"}


def test_log_order_rejects_unknown_columns(logs):
    _, catalogue = logs
    with pytest.raises(ValueError):
        ordering.log_order(catalogue, {"order_id": "x", "colour": "blue"})


def test_append_after_an_unterminated_last_line(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")
    ordering._append_rows(path, ["a", "b"], [{"a": 3, "b": 4}])
    assert ordering.read_rows(path) == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------

def test_build_order_follows_config():
    request = ordering.build_order([SUPERDOVE], AOI, CFG, "test")
    assert request["products"] == [{"item_ids": [SUPERDOVE], "item_type": "PSScene",
                                    "product_bundle": "analytic_8b_sr_udm2"}]
    clip, reproject = request["tools"]           # clip first: only the AOI is resampled
    assert clip == {"clip": {"aoi": AOI}}
    assert reproject == {"reproject": {"projection": "EPSG:5887", "resolution": 3.0,
                                       "kernel": "near"}}
    assert request["delivery"] == {"google_earth_engine": {
        "project": "groupprojectgeog761", "collection": "tonga_psscene"}}


def test_gee_collection_must_be_in_the_project():
    cfg = {**CFG, "gee": {**CFG["gee"], "collection": "projects/someone-else/assets/x"}}
    with pytest.raises(ValueError):
        ordering.build_order([SUPERDOVE], AOI, cfg, "test")


def test_place_order_logs_scenes_and_order(logs):
    ledger, catalogue = logs
    request = ordering.build_order([SUPERDOVE, DOVE_CLASSIC], AOI, CFG, "wharf-test")
    planet = FakePlanet({("POST", ordering.ORDERS_API): [accepted(request)]})

    order_id = ordering.place_order(request, aoi_name=AOI_NAME, ordered_by="Ruofan",
                                    est_km2={SUPERDOVE: 47.5}, session=planet,
                                    ledger=ledger, catalogue=catalogue)

    assert order_id == "order-1"
    assert [method for method, _, _ in planet.calls] == ["POST"]
    assert planet.calls[0][2]["json"] == request
    scenes = ordering.read_rows(ledger)
    assert [r["item_id"] for r in scenes] == [SUPERDOVE, DOVE_CLASSIC]
    assert scenes[0]["est_km2"] == "47.5" and scenes[0]["notes"] == ""
    assert float(scenes[1]["est_km2"]) == pytest.approx(ordering.area_km2(AOI), abs=0.01)
    assert "upper bound" in scenes[1]["notes"]
    assert {(r["state"], r["ordered_by"], r["order_id"]) for r in scenes} == {
        ("queued", "Ruofan", "order-1")}

    (order,) = ordering.read_rows(catalogue)
    assert order["order_id"] == "order-1" and order["n_scenes"] == "2"
    assert (order["start_date"], order["end_date"]) == ("2019-06-23", "2025-01-10")
    assert order["gee_collection"] == "projects/groupprojectgeog761/assets/tonga_psscene"
    assert float(order["quota_used_km2"]) == pytest.approx(
        47.5 + ordering.area_km2(AOI), abs=0.02)


def test_place_order_refuses_a_duplicate_before_calling_planet(logs):
    ledger, catalogue = logs
    write_ledger(ledger, [{"item_id": SUPERDOVE, "aoi": AOI_NAME, "order_id": "old",
                           "state": "success"}])
    planet = FakePlanet()
    request = ordering.build_order([SUPERDOVE], AOI, CFG, "again")
    with pytest.raises(ValueError, match="Already ordered"):
        ordering.place_order(request, aoi_name=AOI_NAME, ordered_by="Ruofan",
                             session=planet, ledger=ledger, catalogue=catalogue)
    assert planet.calls == []


def test_place_order_never_resends_after_a_server_error(logs):
    ledger, catalogue = logs
    request = ordering.build_order([SUPERDOVE], AOI, CFG, "flaky")
    planet = FakePlanet({("POST", ordering.ORDERS_API): [FakeResponse(502, {"message": "x"})]})
    with pytest.raises(RuntimeError, match="502"):
        ordering.place_order(request, aoi_name=AOI_NAME, ordered_by="Ruofan",
                             session=planet, ledger=ledger, catalogue=catalogue)
    assert len(planet.calls) == 1       # it may have gone through: never send it twice
    assert ordering.read_rows(ledger) == []


def test_refresh_ledger_updates_both_logs(logs):
    ledger, catalogue = logs
    request = ordering.build_order([SUPERDOVE], AOI, CFG, "wharf-test")
    planet = FakePlanet({("POST", ordering.ORDERS_API): [accepted(request, "order-1")]})
    ordering.place_order(request, aoi_name=AOI_NAME, ordered_by="Ruofan", session=planet,
                         ledger=ledger, catalogue=catalogue)
    write_ledger(ledger, [{"item_id": DOVE_R, "aoi": AOI_NAME, "order_id": "order-0",
                           "state": "success"}])
    planet.add("GET", f"{ordering.ORDERS_API}/order-1",
               FakeResponse(200, {"id": "order-1", "state": "success"}))

    changes = ordering.refresh_ledger(planet, ledger, catalogue)

    assert changes == [("order-1", "queued", "success")]
    assert {r["order_id"]: r["state"] for r in ordering.read_rows(ledger)} == {
        "order-1": "success", "order-0": "success"}
    assert ordering.read_rows(catalogue)[0]["delivered"] == "yes"
    assert not any(url.endswith("order-0") for _, url, _ in planet.calls)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def test_read_ids_keeps_rows_for_this_aoi(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["aoi", "scene_id", "Weather condition"])
    ws.append(["Nukualofa_wharf.geojson", SUPERDOVE, "clear"])
    ws.append(["Eua.geojson", DOVE_R, "clear"])
    ws.append([None, None, None])
    ws.append(["Nukualofa_wharf.geojson", f" {DOVE_CLASSIC} ", "some clouds"])
    xlsx = tmp_path / "sheet.xlsx"
    wb.save(xlsx)
    assert cli.read_ids(xlsx, AOI_NAME) == [SUPERDOVE, DOVE_CLASSIC]

    sheet_csv = tmp_path / "sheet.csv"
    sheet_csv.write_text(f"﻿AOI,Scene_ID\nNukualofa_wharf.geojson,{SUPERDOVE}\n"
                         f"Eua.geojson,{DOVE_R}\n", encoding="utf-8")
    assert cli.read_ids(sheet_csv, AOI_NAME) == [SUPERDOVE]

    txt = tmp_path / "ids.txt"
    txt.write_text(f"# wharf\n{SUPERDOVE}\n\n{DOVE_R}\n", encoding="utf-8")
    assert cli.read_ids(txt, AOI_NAME) == [SUPERDOVE, DOVE_R]


def test_cli_offline_check(capsys, logs):
    ledger, _ = logs
    code = cli.main(["check", "--offline", "--aoi", str(WHARF_FILE), "--ledger", str(ledger),
                     "--ids", SUPERDOVE, DOVE_CLASSIC, MALFORMED, SUPERDOVE])
    out = capsys.readouterr().out
    assert code == 0
    assert "dropped 1 duplicate" in out
    assert "bad_format" in out and "no_bundle" in out
    assert "Orderable: 1 of 3" in out


def test_cli_order_is_a_dry_run_until_submitted(monkeypatch, capsys, logs):
    ledger, catalogue = logs
    planet = FakePlanet()
    for i in (SUPERDOVE, OTHER_SUPERDOVE):
        planet.add("GET", item_url(i), FakeResponse(200, item(i)))
    monkeypatch.setattr(ordering, "planet_session", lambda *a, **k: planet)
    base = ["order", "--aoi", str(WHARF_FILE), "--ledger", str(ledger),
            "--catalogue", str(catalogue), "--by", "Ruofan"]

    assert cli.main(base + ["--ids", SUPERDOVE]) == 0
    assert "Dry run" in capsys.readouterr().out

    # Two scenes before any order has succeeded: a one-scene test order comes first.
    assert cli.main(base + ["--ids", SUPERDOVE, OTHER_SUPERDOVE, "--submit"]) == 1
    assert "ONE-scene test order" in capsys.readouterr().out
    assert not any(method == "POST" for method, _, _ in planet.calls)

    request = ordering.build_order([SUPERDOVE], AOI, CFG, "test")
    planet.add("POST", ordering.ORDERS_API, accepted(request))
    assert cli.main(base + ["--ids", SUPERDOVE, "--submit"]) == 0
    assert "Order placed: order-1" in capsys.readouterr().out
    assert [r["item_id"] for r in ordering.read_rows(ledger)] == [SUPERDOVE]

    # The same scene again is a duplicate, and nothing more is sent.
    assert cli.main(base + ["--ids", SUPERDOVE, "--submit"]) == 1
    assert "already_ordered" in capsys.readouterr().out
    assert sum(method == "POST" for method, _, _ in planet.calls) == 1


def test_cli_status_offline(capsys, logs):
    ledger, _ = logs
    common = {"aoi": AOI_NAME, "order_id": "o1", "ordered_by": "Ruofan",
              "ordered_at_utc": "2026-10-06T01:02:03Z", "state": "success"}
    write_ledger(ledger, [{"item_id": SUPERDOVE, "est_km2": "47.47", **common},
                          {"item_id": DOVE_R, "est_km2": "20", **common}])
    assert cli.main(["status", "--offline", "--ledger", str(ledger)]) == 0
    out = capsys.readouterr().out
    assert "o1" in out and "67.5" in out
