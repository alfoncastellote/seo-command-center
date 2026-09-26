"""Local map-pack geogrid: run scans and read stored history."""
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import db
from ..providers import dataforseo as dfs


def grid_points(center: tuple[float, float], n: int, spacing_miles: float) -> list[tuple]:
    """N×N grid of (lat,lng) centered on `center`, `spacing_miles` apart."""
    lat0, lng0 = center
    half = (n - 1) / 2.0
    dlat = spacing_miles / 69.0
    dlng = spacing_miles / (69.0 * math.cos(math.radians(lat0)))
    pts = []
    for r in range(n):        # north (top) -> south
        for c in range(n):    # west (left) -> east
            lat = lat0 + (half - r) * dlat
            lng = lng0 + (c - half) * dlng
            pts.append((round(lat, 6), round(lng, 6)))
    return pts


def _brand_rank_at(keyword, lat, lng, zoom, domain, brand_name):
    dom = (domain or "").lower().replace("www.", "")
    bname = (brand_name or "").lower()
    items, cost = dfs.maps_items(keyword, lat, lng, zoom)
    rank, top3 = None, []
    for it in items:
        rg = it.get("rank_group") or it.get("rank_absolute")
        if rg and rg <= 3 and it.get("title"):
            top3.append({"t": (it["title"] or "")[:60], "r": rg})
        if rank is None:
            idom = (it.get("domain") or "").lower().replace("www.", "")
            title = (it.get("title") or "").lower()
            if idom == dom or (dom and idom.endswith("." + dom)) or (bname and bname in title):
                rank = rg
    return rank, top3[:3], cost


def run_brand(brand_id: int, progress=None) -> dict:
    with db.cursor() as con:
        brand = con.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
        grid = con.execute("SELECT * FROM geogrids WHERE brand_id = ?", (brand_id,)).fetchone()
        if not grid:
            raise ValueError(f"brand {brand_id} has no grid configured")
        kws = [r["keyword"] for r in con.execute(
            "SELECT keyword FROM geogrid_keywords WHERE geogrid_id = ? ORDER BY id",
            (grid["id"],),
        ).fetchall()]
    if not brand or not kws:
        raise ValueError("brand or grid keywords missing")
    if not dfs.configured():
        raise RuntimeError(
            "DataForSEO credentials are not configured. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD in the environment, then retry."
        )

    brand_name = brand["name"]
    center = (grid["center_lat"], grid["center_lng"])
    points = grid_points(center, int(grid["grid"]), float(grid["spacing_miles"]))
    zoom = grid["zoom"]
    total = len(points) * len(kws)
    concurrency = int(db.get_setting("concurrency", "8"))
    rows = []
    cost_total = 0.0
    errors = 0
    done = 0

    if progress:
        progress(0, total, f"Scanning {len(kws)} keywords × {len(points)} points…")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(_brand_rank_at, kw, lat, lng, zoom, brand["domain"], brand_name): (kw, lat, lng)
            for kw in kws for (lat, lng) in points
        }
        for fut in as_completed(futures):
            kw, lat, lng = futures[fut]
            try:
                rank, top3, cost = fut.result()
                cost_total += cost
            except Exception:
                rank, top3 = None, []
                errors += 1
            rows.append((kw, lat, lng, rank, top3))
            done += 1
            if progress:
                progress(done, total, f"{done}/{total} pulls · ${cost_total:.4f}")

    order = {(kw, lat, lng): i for i, (kw, lat, lng) in enumerate(futures.values())}
    rows.sort(key=lambda r: order.get((r[0], r[1], r[2]), 0))
    run_at = db.now()

    with db.cursor(commit=True) as con:
        con.executemany(
            "INSERT INTO geogrid_points(run_at, brand_id, brand, keyword, lat, lng, rank, top3) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(run_at, brand_id, brand_name, kw, lat, lng, rank,
              json.dumps(top3) if top3 else None) for (kw, lat, lng, rank, top3) in rows],
        )
    return {"run_at": run_at, "points": len(points), "keywords": len(kws),
            "errors": errors, "cost": round(cost_total, 4)}


def data() -> dict:
    """All grids with full stored history, shaped for the map UI."""
    with db.cursor() as con:
        grids = con.execute(
            "SELECT g.*, b.name, b.domain FROM geogrids g JOIN brands b ON b.id = g.brand_id "
            "ORDER BY b.name"
        ).fetchall()
    brands = []
    for g in grids:
        with db.cursor() as con:
            kws = [r["keyword"] for r in con.execute(
                "SELECT keyword FROM geogrid_keywords WHERE geogrid_id = ? ORDER BY id", (g["id"],)
            ).fetchall()]
            points = con.execute(
                "SELECT run_at, keyword, lat, lng, rank, top3 FROM geogrid_points "
                "WHERE brand_id = ? ORDER BY run_at ASC, id ASC", (g["brand_id"],)
            ).fetchall()
        keywords: dict = {kw: {} for kw in kws}
        for p in points:
            pt = {"lat": p["lat"], "lng": p["lng"], "rank": p["rank"]}
            if p["top3"]:
                try:
                    pt["top3"] = json.loads(p["top3"])
                except ValueError:
                    pass
            keywords.setdefault(p["keyword"], {}).setdefault(p["run_at"], []).append(pt)
        brands.append({
            "id": g["brand_id"],
            "name": g["name"],
            "domain": g["domain"],
            "config": {
                "center": [g["center_lat"], g["center_lng"]],
                "grid": g["grid"],
                "spacing_miles": g["spacing_miles"],
                "zoom": g["zoom"],
            },
            "keywords": keywords,
        })
    return {"brands": brands}


def _save_grid(brand_id, center, size, spacing, zoom, keywords):
    ts = db.now()
    with db.cursor(commit=True) as con:
        existing = con.execute(
            "SELECT id FROM geogrids WHERE brand_id = ?", (brand_id,)
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE geogrids SET center_lat=?, center_lng=?, grid=?, spacing_miles=?, "
                "zoom=?, updated_at=? WHERE brand_id=?",
                (center[0], center[1], size, spacing, zoom, ts, brand_id),
            )
            grid_id = existing["id"]
            con.execute("DELETE FROM geogrid_keywords WHERE geogrid_id = ?", (grid_id,))
        else:
            cur = con.execute(
                "INSERT INTO geogrids(brand_id, center_lat, center_lng, grid, spacing_miles, "
                "zoom, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (brand_id, center[0], center[1], size, spacing, zoom, ts, ts),
            )
            grid_id = cur.lastrowid
        con.executemany(
            "INSERT OR IGNORE INTO geogrid_keywords(geogrid_id, keyword) VALUES (?,?)",
            [(grid_id, k) for k in keywords],
        )
    return grid_id


def set_grid(brand_id, center, size, spacing, keywords, zoom="13z"):
    return _save_grid(brand_id, center, size, spacing, zoom, keywords)


def add_keyword(brand_id, keyword):
    with db.cursor(commit=True) as con:
        grid = con.execute("SELECT id FROM geogrids WHERE brand_id = ?", (brand_id,)).fetchone()
        if not grid:
            raise ValueError("no grid configured for this brand")
        count = con.execute(
            "SELECT COUNT(*) c FROM geogrid_keywords WHERE geogrid_id = ?", (grid["id"],)
        ).fetchone()["c"]
        if count >= 10:
            raise ValueError("a grid can track at most 10 keywords")
        con.execute(
            "INSERT OR IGNORE INTO geogrid_keywords(geogrid_id, keyword) VALUES (?,?)",
            (grid["id"], keyword.strip()),
        )


def remove_keyword(brand_id, keyword):
    with db.cursor(commit=True) as con:
        grid = con.execute("SELECT id FROM geogrids WHERE brand_id = ?", (brand_id,)).fetchone()
        if not grid:
            return
        con.execute(
            "DELETE FROM geogrid_keywords WHERE geogrid_id = ? AND keyword = ?",
            (grid["id"], keyword),
        )


def remove_grid(brand_id):
    with db.cursor(commit=True) as con:
        con.execute("DELETE FROM geogrids WHERE brand_id = ?", (brand_id,))
