"""AI Overview visibility: run scans and read results."""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import db
from ..providers import dataforseo as dfs


def _brand(con, brand_id: int):
    row = con.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    if not row:
        raise ValueError(f"brand {brand_id} not found")
    return row


def _keywords(con, brand_id: int) -> list[str]:
    rows = con.execute(
        "SELECT keyword FROM keywords WHERE brand_id = ? ORDER BY id", (brand_id,)
    ).fetchall()
    seen, out = set(), []
    for r in rows:
        kw = r["keyword"].strip()
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            out.append(kw)
    return out


def run_brand(brand_id: int, progress=None) -> dict:
    """Scan every keyword for a brand and persist one run. Blocking."""
    with db.cursor() as con:
        brand = _brand(con, brand_id)
        keywords = _keywords(con, brand_id)

    if not keywords:
        raise ValueError(f"brand '{brand['name']}' has no keywords to scan")
    if not dfs.configured():
        raise RuntimeError(
            "DataForSEO credentials are not configured. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD in the environment, then retry."
        )

    concurrency = int(db.get_setting("concurrency", "8"))
    total = len(keywords)
    rows: list[dict] = []
    cost_total = 0.0
    errors = 0
    done = 0

    if progress:
        progress(0, total, f"Scanning {total} keywords…")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(dfs.ai_overview, kw, brand["location_code"], brand["language_code"]): kw
            for kw in keywords
        }
        for fut in as_completed(futures):
            kw = futures[fut]
            try:
                res, cost = fut.result()
                cited = dfs.domain_cited(brand["domain"], res["refs"])
                rows.append({"keyword": kw, "has_ai": res["has_ai"],
                             "cited": cited, "refs": res["refs"]})
                cost_total += cost
            except Exception as exc:  # keep the run going on per-keyword failures
                errors += 1
                rows.append({"keyword": kw, "has_ai": False, "cited": False,
                             "refs": [], "error": str(exc)})
            done += 1
            if progress:
                progress(done, total, f"{done}/{total} keywords · ${cost_total:.4f}")

    order = {kw.lower(): i for i, kw in enumerate(keywords)}
    rows.sort(key=lambda r: order.get(r["keyword"].lower(), 0))
    n_ai = sum(1 for r in rows if r["has_ai"])
    n_cited = sum(1 for r in rows if r["cited"])
    ran_at = db.now()

    with db.cursor(commit=True) as con:
        cur = con.execute(
            "INSERT INTO ai_runs(brand_id, ran_at, n_ai, n_cited, total_kw, cost) "
            "VALUES (?,?,?,?,?,?)",
            (brand_id, ran_at, n_ai, n_cited, total, cost_total),
        )
        run_id = cur.lastrowid
        con.executemany(
            "INSERT INTO ai_results(run_id, keyword, has_ai, cited, refs) VALUES (?,?,?,?,?)",
            [(run_id, r["keyword"], int(r["has_ai"]), int(r["cited"]),
              json.dumps(r["refs"])) for r in rows],
        )

    return {"run_id": run_id, "n_ai": n_ai, "n_cited": n_cited, "total": total,
            "errors": errors, "cost": round(cost_total, 4)}


def _top_cited(rows) -> list[dict]:
    counter: Counter = Counter()
    for r in rows:
        for rd in json.loads(r["refs"] or "[]"):
            counter[rd] += 1
    return [{"domain": d, "count": c} for d, c in counter.most_common(12)]


def latest(brand_id: int) -> dict:
    with db.cursor() as con:
        brand = _brand(con, brand_id)
        run = con.execute(
            "SELECT * FROM ai_runs WHERE brand_id = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (brand_id,),
        ).fetchone()
        if not run:
            return {"brand": dict(brand), "run": None, "rows": [], "top_cited": [],
                    "history": []}
        results = con.execute(
            "SELECT * FROM ai_results WHERE run_id = ? ORDER BY id", (run["id"],)
        ).fetchall()
        history = con.execute(
            "SELECT ran_at, n_ai, n_cited, total_kw, cost FROM ai_runs "
            "WHERE brand_id = ? ORDER BY ran_at ASC, id ASC LIMIT 120",
            (brand_id,),
        ).fetchall()

    refs_by_kw = {r["keyword"]: r["refs"] for r in results}
    return {
        "brand": dict(brand),
        "run": dict(run),
        "rows": [{"keyword": r["keyword"], "has_ai": bool(r["has_ai"]),
                  "cited": bool(r["cited"]),
                  "refs": json.loads(r["refs"] or "[]")} for r in results],
        "top_cited": _top_cited(results),
        "history": [dict(h) for h in history],
        "refs_by_kw": refs_by_kw,
    }


def overview() -> list[dict]:
    """All brands with AI visibility counts from their latest run."""
    with db.cursor() as con:
        brands = con.execute("SELECT * FROM brands ORDER BY name").fetchall()
        out = []
        for b in brands:
            run = con.execute(
                "SELECT ran_at, n_ai, n_cited, total_kw, cost FROM ai_runs "
                "WHERE brand_id = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
                (b["id"],),
            ).fetchone()
            kw_count = con.execute(
                "SELECT COUNT(*) c FROM keywords WHERE brand_id = ?", (b["id"],)
            ).fetchone()["c"]
            out.append({
                "id": b["id"], "name": b["name"], "domain": b["domain"],
                "keywords": kw_count,
                "last_run": dict(run) if run else None,
            })
    return out
