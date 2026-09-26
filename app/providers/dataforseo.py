"""Thin DataForSEO client (stdlib only)."""
import base64
import json
import time
import urllib.error
import urllib.request

from .. import config
from . import util

SERP_ORGANIC = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
MAPS_API = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"

COST_AI_PER_KW = 0.0035      # measured
COST_MAP_PER_PULL = 0.002    # measured

USER_AGENT = "seo-visibility-panel/1.0"


class DataForSEOError(RuntimeError):
    pass


def configured() -> bool:
    return bool(config.DATAFORSEO_LOGIN and config.DATAFORSEO_PASSWORD)


def _auth() -> str:
    if not configured():
        raise DataForSEOError(
            "DataForSEO credentials are not configured. Set DATAFORSEO_LOGIN "
            "and DATAFORSEO_PASSWORD in the environment."
        )
    raw = f"{config.DATAFORSEO_LOGIN}:{config.DATAFORSEO_PASSWORD}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _post(url: str, payload, retries: int = 2, timeout: int = 120) -> dict:
    body = json.dumps(payload).encode()
    headers = {
        "Authorization": _auth(),
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            task = (data.get("tasks") or [{}])[0]
            code = task.get("status_code")
            if code and code >= 40000:
                raise DataForSEOError(f"DataForSEO error {code}: {task.get('status_message')}")
            return data
        except DataForSEOError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise DataForSEOError(
                    f"DataForSEO rejected the credentials (HTTP {exc.code}). "
                    "Check DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
                )
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise DataForSEOError(f"DataForSEO request failed: {last_error}")


def ai_overview_search(keyword: str, location_code: int, language_code: str,
                       brand_name: str = "", domain: str = "") -> dict:
    """Google AI Overview (unified provider interface).

    Returns {has_ai, sources, text, cost} for one keyword.
    """
    payload = [{
        "keyword": keyword,
        "location_code": int(location_code),
        "language_code": language_code,
        "device": "desktop",
        "depth": 20,
        "load_async_ai_overview": True,
    }]
    data = _post(SERP_ORGANIC, payload, timeout=120)
    cost = float(data.get("cost") or COST_AI_PER_KW)
    items = ((data["tasks"][0].get("result") or [{}])[0].get("items")) or []
    ai = next((i for i in items if i.get("type") == "ai_overview"), None)
    if not ai:
        return {"has_ai": False, "sources": [], "text": "", "cost": cost}
    sources = []
    for ref in ai.get("references") or []:
        rd = util.clean_domain(ref.get("domain") or "")
        if rd:
            sources.append(rd)
    text = (ai.get("text") or "").strip()
    return {"has_ai": True, "sources": sources, "text": text, "cost": cost}


def maps_items(keyword: str, lat: float, lng: float, zoom: str, depth: int = 20,
               language_code: str = "en") -> tuple[list, float]:
    payload = [{
        "keyword": keyword,
        "location_coordinate": f"{lat},{lng},{zoom}",
        "language_code": language_code,
        "depth": depth,
    }]
    data = _post(MAPS_API, payload, timeout=120)
    cost = float(data.get("cost") or COST_MAP_PER_PULL)
    items = ((data["tasks"][0].get("result") or [{}])[0].get("items")) or []
    return items, cost


def test_credentials() -> dict:
    """Cheap end-to-end check: one Maps pull, returns ok/message/cost."""
    try:
        items, cost = maps_items("restaurant", 40.4168, -3.7038, "13z", language_code="es")
        return {"ok": True, "message": f"Connected — DataForSEO returned {len(items)} results",
                "cost": cost}
    except DataForSEOError as exc:
        return {"ok": False, "message": str(exc), "cost": 0.0}
