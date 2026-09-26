"""Google Gemini provider — generateContent with google_search grounding."""
import json
import urllib.error
import urllib.request

from .. import config
from . import util

GEMINI_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def configured() -> bool:
    return bool(config.GEMINI_API_KEY)


def _raise_http(exc: urllib.error.HTTPError) -> None:
    try:
        detail = json.loads(exc.read().decode(errors="ignore"))
        err = detail.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except Exception:  # noqa: BLE001
        msg = "unknown error"
    raise RuntimeError(f"Gemini error {exc.code}: {msg}")


def search(keyword: str, location_code: int, language_code: str,
           brand_name: str = "", domain: str = "") -> dict:
    url = GEMINI_TEMPLATE.format(model=config.GEMINI_MODEL) + "?key=" + config.GEMINI_API_KEY
    payload = {
        "contents": [{"parts": [{"text": keyword}]}],
        "tools": [{"google_search": {}}],
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        _raise_http(exc)

    text_parts: list[str] = []
    sources: list[str] = []
    for c in data.get("candidates") or []:
        for part in (c.get("content") or {}).get("parts") or []:
            if part.get("text"):
                text_parts.append(part["text"])
        gm = c.get("groundingMetadata") or {}
        for chunk in gm.get("groundingChunks") or []:
            uri = (chunk.get("web") or {}).get("uri")
            if uri:
                d = util.domain_from_url(uri)
                if d:
                    sources.append(d)

    text = "".join(text_parts)
    seen, uniq = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return {"has_ai": True, "sources": uniq, "text": text, "cost": 0.0}
