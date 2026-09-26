"""FastAPI application: UI pages, JSON API, auth, background jobs."""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import auth, config, db, jobs, migrate
from .services import ai_visibility, geogrid

GRID_SIZES = {5, 7, 9}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        imported = migrate.maybe_import()
        if imported:
            print(f"Imported legacy data: {imported}")
    except Exception as exc:  # noqa: BLE001
        print(f"Legacy import skipped: {exc}")
    jobs.start_threads()
    yield


app = FastAPI(title="SEO Visibility Panel", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(config.APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))

PUBLIC_PATHS = {"/login", "/logout", "/healthz"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path.startswith("/favicon") or path in PUBLIC_PATHS:
        return await call_next(request)
    if not auth.valid_token(request.cookies.get(config.SESSION_COOKIE, "")):
        if path.startswith("/api/") or path == "/healthz":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login")
    return await call_next(request)


# ── pages ───────────────────────────────────────────────────────────────────

def _page(request: Request, template: str, active: str):
    return templates.TemplateResponse(
        request, template, {"active": active, "brand_name": config.BRAND_NAME}
    )


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request, "login.html",
        {"brand_name": config.BRAND_NAME, "error": request.query_params.get("error")},
    )


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    if auth.check_access_key(str(form.get("key", ""))):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            config.SESSION_COOKIE, auth.issue_token(),
            max_age=config.SESSION_MAX_AGE, httponly=True, samesite="lax",
        )
        return response
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(config.SESSION_COOKIE)
    return response


@app.get("/")
async def root():
    return RedirectResponse("/ai-visibility")


@app.get("/ai-visibility")
async def ai_visibility_page(request: Request):
    return _page(request, "ai_visibility.html", "ai-visibility")


@app.get("/map-grid")
async def map_grid_page(request: Request):
    return _page(request, "map_grid.html", "map-grid")


@app.get("/brands")
async def brands_page(request: Request):
    return _page(request, "brands.html", "brands")


@app.get("/settings")
async def settings_page(request: Request):
    return _page(request, "settings.html", "settings")


# ── request models ──────────────────────────────────────────────────────────

class BrandIn(BaseModel):
    name: str
    domain: str
    location_code: int = 2840
    language_code: str = "en"


class KeywordIn(BaseModel):
    keyword: str
    tier: str = "target"


class RunIn(BaseModel):
    brand_id: int | str = "all"


class GridIn(BaseModel):
    brand_id: int
    center: list[float]
    grid: int = 7
    spacing_miles: float = 3.5
    keywords: list[str]
    zoom: str = "13z"


class GridKeywordIn(BaseModel):
    keyword: str


# ── brands API ──────────────────────────────────────────────────────────────

def _clean_domain(value: str) -> str:
    dom = value.strip().lower()
    for prefix in ("https://", "http://"):
        if dom.startswith(prefix):
            dom = dom[len(prefix):]
    return dom.split("/")[0].replace("www.", "")


@app.get("/api/brands")
async def api_brands():
    with db.cursor() as con:
        rows = con.execute("SELECT * FROM brands ORDER BY name").fetchall()
        out = []
        for b in rows:
            kws = con.execute(
                "SELECT id, keyword, tier FROM keywords WHERE brand_id = ? ORDER BY id",
                (b["id"],),
            ).fetchall()
            grid = con.execute(
                "SELECT * FROM geogrids WHERE brand_id = ?", (b["id"],)
            ).fetchone()
            gkws = []
            if grid:
                gkws = [r["keyword"] for r in con.execute(
                    "SELECT keyword FROM geogrid_keywords WHERE geogrid_id = ? ORDER BY id",
                    (grid["id"],),
                ).fetchall()]
            out.append({
                "id": b["id"], "name": b["name"], "domain": b["domain"],
                "location_code": b["location_code"], "language_code": b["language_code"],
                "keywords": [dict(k) for k in kws],
                "grid": ({"center": [grid["center_lat"], grid["center_lng"]],
                          "grid": grid["grid"], "spacing_miles": grid["spacing_miles"],
                          "zoom": grid["zoom"], "keywords": gkws} if grid else None),
            })
    return {"brands": out}


@app.post("/api/brands")
async def api_brand_create(payload: BrandIn):
    name, domain = payload.name.strip(), _clean_domain(payload.domain)
    if not name or not domain:
        return JSONResponse({"error": "name and domain are required"}, status_code=400)
    try:
        with db.cursor(commit=True) as con:
            cur = con.execute(
                "INSERT INTO brands(name, domain, location_code, language_code, created_at) "
                "VALUES (?,?,?,?,?)",
                (name, domain, payload.location_code, payload.language_code, db.now()),
            )
            brand_id = cur.lastrowid
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"could not create brand: {exc}"}, status_code=400)
    return {"ok": True, "id": brand_id}


@app.put("/api/brands/{brand_id}")
async def api_brand_update(brand_id: int, payload: BrandIn):
    with db.cursor(commit=True) as con:
        con.execute(
            "UPDATE brands SET name=?, domain=?, location_code=?, language_code=? WHERE id=?",
            (payload.name.strip(), _clean_domain(payload.domain), payload.location_code,
             payload.language_code, brand_id),
        )
    return {"ok": True}


@app.delete("/api/brands/{brand_id}")
async def api_brand_delete(brand_id: int):
    with db.cursor(commit=True) as con:
        con.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
    return {"ok": True}


@app.post("/api/brands/{brand_id}/keywords")
async def api_keyword_add(brand_id: int, payload: KeywordIn):
    kw = payload.keyword.strip()
    if not kw:
        return JSONResponse({"error": "keyword is required"}, status_code=400)
    if payload.tier not in ("target", "brand", "seed"):
        return JSONResponse({"error": "tier must be target, brand or seed"}, status_code=400)
    with db.cursor(commit=True) as con:
        con.execute(
            "INSERT OR IGNORE INTO keywords(brand_id, keyword, tier, created_at) "
            "VALUES (?,?,?,?)",
            (brand_id, kw, payload.tier, db.now()),
        )
    return {"ok": True}


@app.delete("/api/keywords/{keyword_id}")
async def api_keyword_delete(keyword_id: int):
    with db.cursor(commit=True) as con:
        con.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
    return {"ok": True}


# ── AI visibility API ───────────────────────────────────────────────────────

@app.get("/api/ai-visibility")
async def api_ai_overview():
    return {"brands": ai_visibility.overview()}


@app.get("/api/ai-visibility/{brand_id}")
async def api_ai_brand(brand_id: int):
    return ai_visibility.latest(brand_id)


@app.post("/api/ai-visibility/run")
async def api_ai_run(payload: RunIn):
    return _enqueue_runs("ai_visibility", payload.brand_id)


# ── geogrid API ─────────────────────────────────────────────────────────────

@app.get("/api/geogrid")
async def api_geogrid():
    return geogrid.data()


@app.post("/api/geogrid")
async def api_geogrid_set(payload: GridIn):
    lat, lng = payload.center
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JSONResponse({"error": "center must be [lat, lng]"}, status_code=400)
    if payload.grid not in GRID_SIZES:
        return JSONResponse({"error": "grid must be 5, 7 or 9"}, status_code=400)
    if not (0.5 <= payload.spacing_miles <= 15):
        return JSONResponse({"error": "spacing must be 0.5–15 miles"}, status_code=400)
    kws = [k.strip() for k in payload.keywords if k.strip()][:10]
    if not kws:
        return JSONResponse({"error": "at least one keyword is required"}, status_code=400)
    geogrid.set_grid(payload.brand_id, (lat, lng), payload.grid, payload.spacing_miles,
                     kws, payload.zoom)
    return {"ok": True}


@app.post("/api/geogrid/{brand_id}/keywords")
async def api_geogrid_kw_add(brand_id: int, payload: GridKeywordIn):
    try:
        geogrid.add_keyword(brand_id, payload.keyword)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True}


@app.delete("/api/geogrid/{brand_id}/keywords/{keyword}")
async def api_geogrid_kw_remove(brand_id: int, keyword: str):
    geogrid.remove_keyword(brand_id, keyword)
    return {"ok": True}


@app.delete("/api/geogrid/{brand_id}")
async def api_geogrid_remove(brand_id: int):
    geogrid.remove_grid(brand_id)
    return {"ok": True}


@app.post("/api/geogrid/run")
async def api_geogrid_run(payload: RunIn):
    return _enqueue_runs("geogrid", payload.brand_id)


# ── jobs + settings API ─────────────────────────────────────────────────────

@app.get("/api/jobs")
async def api_jobs():
    return {"jobs": jobs.recent()}


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: int):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return job


@app.get("/api/settings")
async def api_settings_get():
    return db.get_settings()


@app.post("/api/settings")
async def api_settings_set(payload: dict):
    allowed = {
        "concurrency", "ai_daily_cap", "geogrid_daily_cap",
        "ai_schedule_enabled", "ai_schedule_dow", "ai_schedule_hour",
        "geogrid_schedule_enabled", "geogrid_schedule_dow", "geogrid_schedule_hour",
        "brand_name", "openai_enabled", "gemini_enabled",
        "own_ai_mode_enabled", "own_chatgpt_enabled", "own_gemini_enabled",
    }
    clean = {k: str(v) for k, v in payload.items() if k in allowed}
    db.set_settings(clean)
    return {"ok": True, "settings": db.get_settings()}


@app.post("/api/demo/seed")
async def api_demo_seed():
    from . import demo
    try:
        demo.seed(force=True)
    except SystemExit as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return {"ok": True}


@app.post("/api/credentials/test")
async def api_credentials_test():
    from .providers import dataforseo as dfs
    return dfs.test_credentials()


@app.get("/api/providers/status")
async def api_providers_status():
    return {"providers": ai_visibility.provider_status()}


# ── helpers ─────────────────────────────────────────────────────────────────

def _cap_key(job_type: str) -> tuple[str, int, str]:
    cap_setting = "ai_daily_cap" if job_type == "ai_visibility" else "geogrid_daily_cap"
    cap = int(db.get_setting(cap_setting, "2") or "2")
    return f"count:{job_type}:{db.today()}", cap, job_type


def _enqueue_runs(job_type: str, brand_ref):
    key, cap, _ = _cap_key(job_type)
    used = db.read_counter(key)
    if used >= cap:
        return JSONResponse(
            {"error": f"Daily limit reached for this tool ({cap}/day). Adjust it in Settings."},
            status_code=429,
        )

    with db.cursor() as con:
        if brand_ref == "all" or brand_ref is None:
            if job_type == "geogrid":
                targets = con.execute(
                    "SELECT b.id, b.name FROM brands b JOIN geogrids g ON g.brand_id=b.id "
                    "WHERE (SELECT COUNT(*) FROM geogrid_keywords k WHERE k.geogrid_id=g.id)>0"
                ).fetchall()
            else:
                targets = con.execute(
                    "SELECT b.id, b.name FROM brands b WHERE "
                    "(SELECT COUNT(*) FROM keywords k WHERE k.brand_id=b.id)>0"
                ).fetchall()
        else:
            row = con.execute(
                "SELECT id, name FROM brands WHERE id = ?", (int(brand_ref),)
            ).fetchone()
            targets = [row] if row else []

    if not targets:
        return JSONResponse({"error": "nothing to scan — configure a brand first"}, status_code=400)

    job_ids = [jobs.enqueue(job_type, t["id"], t["name"]) for t in targets]
    db.bump_counter(key, 1)
    return {"ok": True, "jobs": job_ids, "brands": [t["name"] for t in targets],
            "used": used + 1, "limit": cap}
