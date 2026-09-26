"""OpenWebNinja provider — Google AI Overviews + ChatGPT/Gemini relays.

One key serves three engines:
  - /ai-overviews   -> Google Search AI Overview (text + reference links)
  - /chatgpt/chat   -> ChatGPT (web access)
  - /gemini/chat    -> Gemini (web access)

Auth: `x-api-key` header. Each API must be subscribed in the OpenWeb Ninja
dashboard first (they have free tiers).
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .. import config
from . import util

BASE = "https://api.openwebninja.com"

URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
COST_PER_QUERY = 0.0


def configured() -> bool:
    return bool(config.OPENWEBNINJA_API_KEY)


def _headers() -> dict:
    return {"x-api-key": config.OPENWEBNINJA_API_KEY, "Content-Type": "application/json"}


def _raise_http(exc: urllib.error.HTTPError) -> None:
    raw = exc.read().decode(errors="ignore")
    msg = "unknown error"
    try:
        detail = json.loads(raw)
        err = detail.get("error") or {}
        if isinstance(err, dict) and err.get("message"):
            msg = err["message"]
        elif isinstance(detail, dict) and detail.get("message"):
            msg = detail["message"]
        else:
            msg = raw[:300]
    except Exception:  # noqa: BLE001
        msg = raw[:300] or "unknown error"
    raise RuntimeError(f"OpenWebNinja error {exc.code}: {msg}")


def _get(path: str, params: dict) -> dict:
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        _raise_http(exc)


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        _raise_http(exc)


def _extract(data) -> tuple[str, list[str]]:
    """Best-effort: longest string = answer text; every URL = source."""
    strings: list[str] = []
    urls: list[str] = []

    def walk(o) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            strings.append(o)
            for u in URL_RE.findall(o):
                urls.append(u.rstrip(".,;:!?()"))

    walk(data)
    text = max(strings, key=len) if strings else ""
    return text, urls


def _finish(data) -> dict:
    text, urls = _extract(data)
    seen, sources = set(), []
    for u in urls:
        d = util.domain_from_url(u)
        if d and d not in seen and d not in ("openwebninja.com", "www.openwebninja.com"):
            seen.add(d)
            sources.append(d)
    return {"has_ai": True, "sources": sources, "text": text, "cost": COST_PER_QUERY}


def _gl(language_code: str) -> str:
    return "es" if (language_code or "").lower() == "es" else "us"


def ai_overviews_search(keyword: str, location_code: int, language_code: str,
                        brand_name: str = "", domain: str = "") -> dict:
    data = _get("/ai-overviews", {"q": keyword, "gl": _gl(language_code),
                                  "hl": language_code or "en"})
    return _finish(data)


def chatgpt_search(keyword: str, location_code: int, language_code: str,
                   brand_name: str = "", domain: str = "") -> dict:
    data = _post("/chatgpt/chat", {"message": keyword, "markdown": True})
    return _finish(data)


def gemini_search(keyword: str, location_code: int, language_code: str,
                  brand_name: str = "", domain: str = "") -> dict:
    data = _post("/gemini/chat", {"message": keyword, "markdown": True})
    return _finish(data)
