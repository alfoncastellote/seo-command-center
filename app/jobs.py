"""Background job engine and lightweight scheduler (daemon threads)."""
import datetime
import threading
import time
import traceback

from . import db
from .services import ai_visibility, geogrid

_started = False
_lock = threading.Lock()

TYPE_LABELS = {"ai_visibility": "AI Visibility", "geogrid": "Map Grid"}


def enqueue(job_type: str, brand_id: int, brand: str = "") -> int:
    with db.cursor(commit=True) as con:
        cur = con.execute(
            "INSERT INTO jobs(type, brand_id, brand, status, created_at) VALUES (?,?,?,?,?)",
            (job_type, brand_id, brand, "queued", db.now()),
        )
        return cur.lastrowid


def get(job_id: int) -> dict | None:
    with db.cursor() as con:
        row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def recent(limit: int = 15) -> list[dict]:
    with db.cursor() as con:
        rows = con.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def _update(job_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db.cursor(commit=True) as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def _execute(job: dict) -> None:
    job_id, job_type, brand_id = job["id"], job["type"], job["brand_id"]
    _update(job_id, status="running", started_at=db.now(), message="Starting…")

    def progress(done, total, message):
        _update(job_id, progress=done, total=total, message=message)

    if job_type == "ai_visibility":
        result = ai_visibility.run_brand(brand_id, progress)
        summary = (f"{result['n_cited']} citations across {result['total']} engine checks")
    elif job_type == "geogrid":
        result = geogrid.run_brand(brand_id, progress)
        summary = (f"{result['points']} points × {result['keywords']} keywords")
    else:
        raise ValueError(f"unknown job type {job_type}")
    if result.get("errors"):
        summary += f" · {result['errors']} pulls failed"
        if result.get("first_error"):
            summary += f" ({result['first_error']})"

    _update(job_id, status="done", finished_at=db.now(),
            progress=result.get("total", result.get("points", 0)),
            total=result.get("total", result.get("points", 0)),
            cost=result.get("cost", 0), message=summary)


def _worker() -> None:
    while True:
        try:
            with db.cursor(commit=True) as con:
                row = con.execute(
                    "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
                ).fetchone()
                if row:
                    con.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
            if row:
                try:
                    _execute(dict(row))
                except Exception as exc:  # noqa: BLE001
                    _update(job_id=row["id"], status="error", finished_at=db.now(),
                            error=str(exc), message="Failed")
                    traceback.print_exc()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(2)


def _brands_for(job_type: str) -> list[dict]:
    with db.cursor() as con:
        if job_type == "geogrid":
            rows = con.execute(
                "SELECT b.id, b.name FROM brands b JOIN geogrids g ON g.brand_id = b.id "
                "WHERE (SELECT COUNT(*) FROM geogrid_keywords k WHERE k.geogrid_id = g.id) > 0 "
                "ORDER BY b.name"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT b.id, b.name FROM brands b WHERE "
                "(SELECT COUNT(*) FROM keywords k WHERE k.brand_id = b.id) > 0 ORDER BY b.name"
            ).fetchall()
    return [dict(r) for r in rows]


def _mark_scheduled(job_type: str, day: str) -> None:
    db.set_settings({f"last_sched_{job_type}": day})


def _scheduler_tick() -> None:
    now = datetime.datetime.now()
    day = now.date().isoformat()
    settings = db.get_settings()
    for job_type in ("ai_visibility", "geogrid"):
        prefix = "ai" if job_type == "ai_visibility" else "geogrid"
        if settings.get(f"{prefix}_schedule_enabled", "1") != "1":
            continue
        try:
            dow = int(settings.get(f"{prefix}_schedule_dow", "1"))
            hour = int(settings.get(f"{prefix}_schedule_hour", "6"))
        except ValueError:
            continue
        if now.weekday() != dow % 7 or now.hour != hour:
            continue
        if settings.get(f"last_sched_{job_type}") == day:
            continue
        for brand in _brands_for(job_type):
            enqueue(job_type, brand["id"], brand["name"])
        _mark_scheduled(job_type, day)


def _scheduler() -> None:
    while True:
        try:
            _scheduler_tick()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(60)


def start_threads() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_worker, name="svp-worker", daemon=True).start()
    threading.Thread(target=_scheduler, name="svp-scheduler", daemon=True).start()
