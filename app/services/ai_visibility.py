"""AI visibility: run scans across multiple engines and read results."""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import db
from ..providers import dataforseo as dfs
from ..providers import gemini as gemini_prov
from ..providers import openai as openai_prov
from ..providers import openwebninja as own
from ..providers import util

PROVIDERS = {
    "google_ai_overview": {
        "label": "Google AI Overview",
        "configured": dfs.configured,
        "search": dfs.ai_overview_search,
    },
    "openai": {
        "label": "ChatGPT",
        "configured": openai_prov.configured,
        "search": openai_prov.search,
    },
    "gemini": {
        "label": "Gemini",
        "configured": gemini_prov.configured,
        "search": gemini_prov.search,
    },
    "own_ai_overviews": {
        "label": "Google AI Overview · OpenWebNinja",
        "configured": own.configured,
        "search": own.ai_overviews_search,
    },
    "own_ai_mode": {
        "label": "Google AI Mode · OpenWebNinja",
        "configured": own.configured,
        "search": own.ai_mode_search,
    },
    "own_chatgpt": {
        "label": "ChatGPT · OpenWebNinja",
        "configured": own.configured,
        "search": own.chatgpt_search,
    },
    "own_gemini": {
        "label": "Gemini · OpenWebNinja",
        "configured": own.configured,
        "search": own.gemini_search,
    },
    "own_copilot": {
        "label": "Copilot · OpenWebNinja",
        "configured": own.configured,
        "search": own.copilot_search,
    },
}


def enabled_providers() -> list[tuple[str, dict]]:
    """Providers that are configured (key present) and enabled in settings."""
    flags = db.get_settings()
    out = []
    for key, meta in PROVIDERS.items():
        if flags.get(f"{key}_enabled", "1") != "1":
            continue
        if not meta["configured"]():
            continue
        out.append((key, meta))
    return out


def provider_status() -> list[dict]:
    flags = db.get_settings()
    out = []
    for key, meta in PROVIDERS.items():
        out.append({
            "key": key,
            "label": meta["label"],
            "configured": bool(meta["configured"]()),
            "enabled": flags.get(f"{key}_enabled", "1") == "1",
        })
    return out


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


def _run_one(pkey: str, kw: str, brand) -> dict:
    meta = PROVIDERS[pkey]
    res = meta["search"](kw, brand["location_code"], brand["language_code"],
                         brand["name"], brand["domain"])
    sources = res.get("sources") or []
    return {
        "provider": pkey,
        "keyword": kw,
        "has_ai": bool(res.get("has_ai", True)),
        "cited": util.domain_cited(brand["domain"], sources),
        "mentioned": util.brand_mentioned(brand["name"], brand["domain"], res.get("text") or ""),
        "sources": sources,
        "snippet": (res.get("text") or "")[:400],
        "cost": float(res.get("cost") or 0.0),
    }


def run_brand(brand_id: int, progress=None) -> dict:
    """Scan every keyword on every enabled engine and persist one run. Blocking."""
    with db.cursor() as con:
        brand = _brand(con, brand_id)
        keywords = _keywords(con, brand_id)

    if not keywords:
        raise ValueError(f"brand '{brand['name']}' has no keywords to scan")
    providers = enabled_providers()
    if not providers:
        raise RuntimeError(
            "No AI engine is configured. Set DATAFORSEO_LOGIN/PASSWORD, OPENAI_API_KEY "
            "or GEMINI_API_KEY (and enable it in Settings)."
        )

    concurrency = int(db.get_setting("concurrency", "8"))
    tasks = [(pkey, kw) for pkey, _ in providers for kw in keywords]
    total = len(tasks)
    rows: list[dict] = []
    cost_total = 0.0
    errors = 0
    first_error = None
    done = 0

    if progress:
        progress(0, total, f"Scanning {len(keywords)} keywords × {len(providers)} engines…")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_run_one, pkey, kw, brand): (pkey, kw) for pkey, kw in tasks}
        for fut in as_completed(futures):
            pkey, kw = futures[fut]
            try:
                r = fut.result()
                rows.append(r)
                cost_total += r["cost"]
            except Exception as exc:  # noqa: BLE001
                errors += 1
                if first_error is None:
                    first_error = f"{PROVIDERS[pkey]['label']}: {exc}"
                rows.append({"provider": pkey, "keyword": kw, "has_ai": False,
                             "cited": False, "mentioned": False, "sources": [],
                             "snippet": "", "cost": 0.0, "error": str(exc)})
            done += 1
            if progress:
                progress(done, total, f"{done}/{total} checks · ${cost_total:.4f}")

    if errors and errors == total:
        raise RuntimeError(f"All {total} checks failed — {first_error}")

    ran_at = db.now()
    n_ai = sum(1 for r in rows if r["has_ai"])
    n_cited = sum(1 for r in rows if r["cited"])
    with db.cursor(commit=True) as con:
        cur = con.execute(
            "INSERT INTO ai_runs(brand_id, ran_at, n_ai, n_cited, total_kw, cost) "
            "VALUES (?,?,?,?,?,?)",
            (brand_id, ran_at, n_ai, n_cited, len(keywords), cost_total),
        )
        run_id = cur.lastrowid
        con.executemany(
            "INSERT INTO ai_results(run_id, provider, keyword, has_ai, mentioned, cited, "
            "refs, snippet) VALUES (?,?,?,?,?,?,?,?)",
            [(run_id, r["provider"], r["keyword"], int(r["has_ai"]), int(r["mentioned"]),
              int(r["cited"]), json.dumps(r["sources"]), r["snippet"]) for r in rows],
        )

    return {"run_id": run_id, "total": total, "n_ai": n_ai, "n_cited": n_cited,
            "errors": errors, "first_error": first_error, "cost": round(cost_total, 4)}


def latest(brand_id: int) -> dict:
    with db.cursor() as con:
        brand = _brand(con, brand_id)
        run = con.execute(
            "SELECT * FROM ai_runs WHERE brand_id = ? ORDER BY ran_at DESC, id DESC LIMIT 1",
            (brand_id,),
        ).fetchone()
        if not run:
            return {"brand": dict(brand), "run": None, "providers": [], "rows": [],
                    "top_cited": {}, "history": []}
        results = con.execute(
            "SELECT * FROM ai_results WHERE run_id = ? ORDER BY id", (run["id"],)
        ).fetchall()
        history = con.execute(
            "SELECT r.ran_at, x.provider, COUNT(*) n, SUM(x.has_ai) has_ai, "
            "SUM(x.mentioned) mentioned, SUM(x.cited) cited "
            "FROM ai_runs r JOIN ai_results x ON x.run_id = r.id "
            "WHERE r.brand_id = ? GROUP BY r.id, x.provider "
            "ORDER BY r.ran_at ASC, r.id ASC LIMIT 500",
            (brand_id,),
        ).fetchall()

    prov_summary = []
    for pkey, meta in PROVIDERS.items():
        subset = [r for r in results if r["provider"] == pkey]
        if not subset:
            continue
        prov_summary.append({
            "key": pkey, "label": meta["label"], "n": len(subset),
            "has_ai": sum(1 for r in subset if r["has_ai"]),
            "mentioned": sum(1 for r in subset if r["mentioned"]),
            "cited": sum(1 for r in subset if r["cited"]),
        })

    rows = [{
        "keyword": r["keyword"], "provider": r["provider"],
        "has_ai": bool(r["has_ai"]), "mentioned": bool(r["mentioned"]),
        "cited": bool(r["cited"]), "sources": json.loads(r["refs"] or "[]"),
        "snippet": r["snippet"],
    } for r in results]

    top_cited = {}
    for pkey in PROVIDERS:
        counter: Counter = Counter()
        for r in results:
            if r["provider"] == pkey:
                for d in json.loads(r["refs"] or "[]"):
                    counter[d] += 1
        top_cited[pkey] = [{"domain": d, "count": c} for d, c in counter.most_common(12)]

    return {
        "brand": dict(brand),
        "run": dict(run),
        "providers": prov_summary,
        "rows": rows,
        "top_cited": top_cited,
        "history": [dict(h) for h in history],
    }


def overview() -> list[dict]:
    """All brands with counts from their latest run."""
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
