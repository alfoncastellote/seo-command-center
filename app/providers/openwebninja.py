"""OpenWebNinja "AI Answers" provider — five sources under one key.

Endpoints (same key, `x-api-key` header):
  - /ai-overviews/ai-overviews   GET  -> Google AI Overviews (text_parts + reference_links)
  - /google-ai-mode/ai-mode      GET  -> Google AI Mode (reply_parts + reference_links)
  - /chatgpt/chat                POST -> ChatGPT (reply_text + content_references)
  - /gemini/chat                 POST -> Gemini (reply_text + reference_links)
  - /copilot/copilot             POST -> Copilot (message + citations)

Each API must be subscribed in the OpenWeb Ninja dashboard (free tiers).
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


def _gl(language_code: str) -> str:
    return "es" if (language_code or "").lower() == "es" else "us"


def _dedupe(urls: list[str]) -> list[str]:
    seen, sources = set(), []
    for u in urls:
        d = util.domain_from_url(u)
        if d and d not in seen and d not in ("openwebninja.com", "www.openwebninja.com"):
            seen.add(d)
            sources.append(d)
    return sources


def _find_urls(obj) -> list[str]:
    urls: list[str] = []

    def walk(o) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for u in URL_RE.findall(o):
                urls.append(u.rstrip(".,;:!?()"))

    walk(obj)
    return urls


def _join_parts(parts) -> str:
    out: list[str] = []
    for p in parts or []:
        if not isinstance(p, dict):
            continue
        if p.get("text"):
            out.append(p["text"])
        for it in p.get("list") or []:
            if isinstance(it, dict):
                if it.get("title"):
                    out.append(it["title"])
                if it.get("text"):
                    out.append(it["text"])
    return " ".join(out)


def ai_overviews_search(keyword: str, location_code: int, language_code: str,
                        brand_name: str = "", domain: str = "") -> dict:
    data = _get("/ai-overviews/ai-overviews",
                {"q": keyword, "gl": _gl(language_code), "hl": language_code or "en"})
    d = data.get("data") or {}
    urls = [r.get("link") or "" for r in (d.get("reference_links") or []) if isinstance(r, dict)]
    return {"has_ai": True, "sources": _dedupe(urls), "text": _join_parts(d.get("text_parts")),
            "cost": COST_PER_QUERY}


def ai_mode_search(keyword: str, location_code: int, language_code: str,
                   brand_name: str = "", domain: str = "") -> dict:
    data = _get("/google-ai-mode/ai-mode",
                {"prompt": keyword, "gl": _gl(language_code), "hl": language_code or "en"})
    d = data.get("data") or {}
    urls = [r.get("link") or "" for r in (d.get("reference_links") or []) if isinstance(r, dict)]
    return {"has_ai": True, "sources": _dedupe(urls), "text": _join_parts(d.get("reply_parts")),
            "cost": COST_PER_QUERY}


def chatgpt_search(keyword: str, location_code: int, language_code: str,
                   brand_name: str = "", domain: str = "") -> dict:
    data = _post("/chatgpt/chat", {"message": keyword, "markdown": True})
    d = data.get("data") or {}
    text = d.get("reply_text") or ""
    urls = _find_urls(d.get("content_references"))
    return {"has_ai": True, "sources": _dedupe(urls), "text": text, "cost": COST_PER_QUERY}


def gemini_search(keyword: str, location_code: int, language_code: str,
                  brand_name: str = "", domain: str = "") -> dict:
    data = _post("/gemini/chat", {"message": keyword, "markdown": True})
    d = data.get("data") or {}
    text = d.get("reply_text") or ""
    urls = [r.get("link") or "" for r in (d.get("reference_links") or []) if isinstance(r, dict)]
    return {"has_ai": True, "sources": _dedupe(urls), "text": text, "cost": COST_PER_QUERY}


def copilot_search(keyword: str, location_code: int, language_code: str,
                   brand_name: str = "", domain: str = "") -> dict:
    data = _post("/copilot/copilot", {"message": [keyword]})
    d = data.get("data") or {}
    text = d.get("message") or ""
    urls = [c.get("url") or "" for c in (d.get("citations") or []) if isinstance(c, dict)]
    return {"has_ai": True, "sources": _dedupe(urls), "text": text, "cost": COST_PER_QUERY}
