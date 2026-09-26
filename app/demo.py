"""Seed realistic sample data so the panel can be explored without API credits.

    python -m app.demo [--force]
"""
import datetime
import json
import math
import random
import sys

from . import db
from .services.geogrid import grid_points

random.seed(42)

BRANDS = [
    {"name": "BrightSmile Dental", "domain": "brightsmile.dental",
     "location_code": 2840, "language_code": "en",
     "keywords": ["dentist near me", "teeth whitening", "emergency dentist austin",
                  "invisalign austin", "dental implants", "root canal cost"],
     "grid": {"center": [30.2672, -97.7431], "size": 7, "spacing": 2.5,
              "keywords": ["dentist", "emergency dentist"]}},
    {"name": "Acme Coffee", "domain": "acmecoffee.com",
     "location_code": 2840, "language_code": "en",
     "keywords": ["best coffee subscription", "fresh roasted coffee beans",
                  "single origin espresso", "light roast coffee online"],
     "grid": None},
]

CITED = ["healthline.com", "webmd.com", "yelp.com", "colgate.com", "mayoclinic.org",
         "ada.org", "reddit.com"]


def _kw_brand_id(con, name):
    return con.execute("SELECT id FROM brands WHERE name = ?", (name,)).fetchone()["id"]


def seed(force: bool = False) -> None:
    db.init_db()
    with db.cursor() as con:
        existing = con.execute("SELECT COUNT(*) c FROM brands").fetchone()["c"]
    if existing and not force:
        raise SystemExit("Database already has brands — pass --force to reseed (destructive).")

    with db.cursor(commit=True) as con:
        if force:
            for table in ("ai_results", "ai_runs", "geogrid_points", "geogrid_keywords",
                          "geogrids", "keywords", "brands", "jobs"):
                con.execute(f"DELETE FROM {table}")
        ts = db.now()
        for b in BRANDS:
            cur = con.execute(
                "INSERT INTO brands(name, domain, location_code, language_code, created_at) "
                "VALUES (?,?,?,?,?)",
                (b["name"], b["domain"], b["location_code"], b["language_code"], ts),
            )
            brand_id = cur.lastrowid
            for i, kw in enumerate(b["keywords"]):
                tier = "brand" if i == 0 else "target"
                con.execute(
                    "INSERT INTO keywords(brand_id, keyword, tier, created_at) VALUES (?,?,?,?)",
                    (brand_id, kw, tier, ts),
                )
            if b["grid"]:
                g = b["grid"]
                gcur = con.execute(
                    "INSERT INTO geogrids(brand_id, center_lat, center_lng, grid, "
                    "spacing_miles, zoom, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (brand_id, g["center"][0], g["center"][1], g["size"], g["spacing"],
                     "13z", ts, ts),
                )
                gid = gcur.lastrowid
                for kw in g["keywords"]:
                    con.execute(
                        "INSERT INTO geogrid_keywords(geogrid_id, keyword) VALUES (?,?)",
                        (gid, kw),
                    )

    _seed_ai_runs()
    _seed_grid_runs()


def _seed_ai_runs() -> None:
    today = datetime.datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
    with db.cursor(commit=True) as con:
        for b in BRANDS:
            brand_id = _kw_brand_id(con, b["name"])
            base_ai = random.randint(3, 5)
            base_cited = random.randint(1, 3)
            for weeks_ago in range(5, -1, -1):
                ran_at = (today - datetime.timedelta(days=weeks_ago * 7)).strftime("%Y-%m-%d %H:%M:%S")
                rows = []
                n_ai = n_cited = 0
                for kw in b["keywords"]:
                    has_ai = random.random() < (base_ai / len(b["keywords"])) + 0.15
                    cited = has_ai and random.random() < 0.45
                    refs = random.sample(CITED, random.randint(2, 4)) if has_ai else []
                    if cited:
                        refs.insert(0, b["domain"])
                        n_cited += 1
                    if has_ai:
                        n_ai += 1
                    rows.append((kw, int(has_ai), int(cited), json.dumps(refs)))
                cur = con.execute(
                    "INSERT INTO ai_runs(brand_id, ran_at, n_ai, n_cited, total_kw, cost) "
                    "VALUES (?,?,?,?,?,?)",
                    (brand_id, ran_at, n_ai, n_cited, len(b["keywords"]),
                     round(len(b["keywords"]) * 0.0035, 4)),
                )
                run_id = cur.lastrowid
                con.executemany(
                    "INSERT INTO ai_results(run_id, keyword, has_ai, cited, refs) "
                    "VALUES (?,?,?,?,?)",
                    [(run_id, *r) for r in rows],
                )


def _seed_grid_runs() -> None:
    today = datetime.datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    comps = ["Downtown Dental Studio", "Lakeside Family Dentistry", "Capitol Smiles"]
    with db.cursor(commit=True) as con:
        for b in BRANDS:
            if not b["grid"]:
                continue
            g = b["grid"]
            brand_id = _kw_brand_id(con, b["name"])
            pts = grid_points(tuple(g["center"]), g["size"], g["spacing"])
            for weeks_ago in range(3, -1, -1):
                run_at = (today - datetime.timedelta(days=weeks_ago * 7)).strftime("%Y-%m-%d %H:%M:%S")
                rows = []
                for kw in g["keywords"]:
                    for (lat, lng) in pts:
                        dist = math.hypot(
                            (lat - g["center"][0]) * 69.0 / g["spacing"],
                            (lng - g["center"][1]) * 69.0 * math.cos(math.radians(g["center"][0])) / g["spacing"],
                        )
                        improvement = (3 - weeks_ago) * 0.6
                        rank = None
                        if dist <= 2.4 + improvement or random.random() < 0.25:
                            rank = max(1, int(dist * 1.4 - improvement + random.random() * 3))
                        top3 = [{"t": t, "r": i + 1} for i, t in enumerate(random.sample(comps, 2))]
                        if rank and rank <= 3:
                            top3.insert(rank - 1, {"t": b["name"], "r": rank})
                        top3 = [{"t": x["t"], "r": i + 1} for i, x in enumerate(top3[:3])]
                        rows.append((run_at, brand_id, b["name"], kw, lat, lng, rank,
                                     json.dumps(top3) if top3 else None))
                con.executemany(
                    "INSERT INTO geogrid_points(run_at, brand_id, brand, keyword, lat, lng, "
                    "rank, top3) VALUES (?,?,?,?,?,?,?,?)",
                    rows,
                )


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
    print("Demo data seeded.")
