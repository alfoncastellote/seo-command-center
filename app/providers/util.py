"""Shared helpers for AI-visibility providers."""
from urllib.parse import urlparse


def clean_domain(value: str) -> str:
    dom = (value or "").strip().lower()
    if dom.startswith("www."):
        dom = dom[4:]
    return dom


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc
    except ValueError:
        host = ""
    return clean_domain(host)


def domain_cited(domain: str, sources: list) -> bool:
    dom = clean_domain(domain)
    if not dom:
        return False
    return any(s == dom or s.endswith("." + dom) for s in sources if s)


def brand_mentioned(brand_name: str, domain: str, text: str) -> bool:
    """True if the brand name or its domain appears in the answer text."""
    t = (text or "").lower()
    needles = []
    if brand_name:
        n = brand_name.strip().lower()
        if n:
            needles.append(n)
    if domain:
        d = clean_domain(domain)
        if d:
            needles.append(d)
    return any(n in t for n in needles)
