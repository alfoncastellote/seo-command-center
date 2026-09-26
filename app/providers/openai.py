"""OpenAI (ChatGPT) provider — Responses API with web_search."""
import json
import urllib.error
import urllib.request

from .. import config
from . import util

RESPONSES_API = "https://api.openai.com/v1/responses"

# Approximate cost per query for gpt-4o-mini web search (tokens + search fee).
COST_PER_QUERY = 0.005


def configured() -> bool:
    return bool(config.OPENAI_API_KEY)


def _raise_http(exc: urllib.error.HTTPError) -> None:
    try:
        detail = json.loads(exc.read().decode(errors="ignore"))
        err = detail.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except Exception:  # noqa: BLE001
        msg = "unknown error"
    raise RuntimeError(f"OpenAI error {exc.code}: {msg}")


def search(keyword: str, location_code: int, language_code: str,
           brand_name: str = "", domain: str = "") -> dict:
    prompt = (
        "You are a search assistant. Answer the user's query directly and cite the "
        "sources you used.\n\nUser query: " + keyword +
        "\n\nAnswer in the same language as the query."
    )
    body = json.dumps({
        "model": config.OPENAI_MODEL,
        "input": prompt,
        "tools": [{"type": "web_search"}],
    }).encode()
    req = urllib.request.Request(
        RESPONSES_API, data=body, method="POST",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        _raise_http(exc)

    text_parts: list[str] = []
    sources: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    text_parts.append(c.get("text") or "")
                for a in c.get("annotations") or []:
                    if a.get("type") == "url_citation" and a.get("url"):
                        d = util.domain_from_url(a["url"])
                        if d:
                            sources.append(d)

    text = "\n".join(text_parts)
    seen, uniq = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return {"has_ai": True, "sources": uniq, "text": text, "cost": COST_PER_QUERY}
