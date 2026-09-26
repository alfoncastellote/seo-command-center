"""One-time import from the original SEO Command Center data files.

Reads data/keywords.json (brands + keywords + geogrid config) and
data/ranks.db (geogrid point history) if they exist and the new database
is still empty. Safe to run on every boot.
"""
import json
import sqlite3

from . import config, db


def _domain(value: str) -> str:
    dom = (value or "").strip().lower()
    for prefix in ("https://", "http://"):
        if dom.startswith(prefix):
            dom = dom[len(prefix):]
    return dom.split("/")[0].replace("www.", "")


def maybe_import() -> dict | None:
    keywords_file = config.DATA_DIR / "keywords.json"
    if not keywords_file.exists():
        return None
    with db.cursor() as con:
        if con.execute("SELECT COUNT(*) c FROM brands").fetchone()["c"]:
            return None

    try:
        cfg = json.loads(keywords_file.read_text())
    except (ValueError, OSError):
        return None

    imported = {"brands": 0, "keywords": 0, "geogrid_points": 0}
    ts = db.now()
    with db.cursor(commit=True) as con:
        for name, meta in (cfg.get("brands") or {}).items():
            domain = _domain(meta.get("domain", ""))
            if not domain:
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO brands(name, domain, location_code, language_code, "
                "created_at) VALUES (?,?,?,?,?)",
                (name, domain, int(meta.get("location_code", 2840)),
                 meta.get("language_code", "en"), ts),
            )
            if cur.lastrowid is None:
                continue
            brand_id = cur.lastrowid
            imported["brands"] += 1

            tiers = (("target_keywords", "target"), ("seed_keywords", "seed"),
                     ("brand_keywords", "brand"), ("local_keywords", "target"))
            seen = set()
            for field, tier in tiers:
                for kw in meta.get(field) or []:
                    kw = str(kw).strip()
                    if not kw or kw.lower() in seen:
                        continue
                    seen.add(kw.lower())
                    con.execute(
                        "INSERT OR IGNORE INTO keywords(brand_id, keyword, tier, created_at) "
                        "VALUES (?,?,?,?)", (brand_id, kw, tier, ts),
                    )
                    imported["keywords"] += 1

            gg = meta.get("geogrid")
            if gg and gg.get("center"):
                gcur = con.execute(
                    "INSERT OR IGNORE INTO geogrids(brand_id, center_lat, center_lng, grid, "
                    "spacing_miles, zoom, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (brand_id, gg["center"][0], gg["center"][1], int(gg.get("grid", 7)),
                     float(gg.get("spacing_miles", 3.5)), gg.get("zoom", "13z"), ts, ts),
                )
                gid = gcur.lastrowid
                if gid:
                    for kw in gg.get("keywords") or []:
                        con.execute(
                            "INSERT OR IGNORE INTO geogrid_keywords(geogrid_id, keyword) "
                            "VALUES (?,?)", (gid, kw),
                        )

    imported["geogrid_points"] = _import_geogrid_points()
    return imported


def _import_geogrid_points() -> int:
    old = config.DATA_DIR / "ranks.db"
    if not old.exists():
        return 0
    try:
        src = sqlite3.connect(old)
        rows = src.execute(
            "SELECT checked_at, brand, keyword, lat, lng, rank, top3 FROM geogrid"
        ).fetchall()
        src.close()
    except sqlite3.Error:
        return 0
    if not rows:
        return 0

    count = 0
    with db.cursor(commit=True) as con:
        brands = {r["name"]: r["id"] for r in con.execute("SELECT id, name FROM brands")}
        for checked_at, brand, keyword, lat, lng, rank, top3 in rows:
            brand_id = brands.get(brand)
            if not brand_id:
                continue
            con.execute(
                "INSERT INTO geogrid_points(run_at, brand_id, brand, keyword, lat, lng, rank, "
                "top3) VALUES (?,?,?,?,?,?,?,?)",
                (checked_at, brand_id, brand, keyword, lat, lng, rank, top3),
            )
            count += 1
    return count
