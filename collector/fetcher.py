import requests
import trafilatura

from collector.rate_limit import safe_get


def fetch_article(url: str) -> tuple[str, str] | None:
    try:
        r = safe_get(url, timeout=15)
    except requests.RequestException as e:
        print(f"[fetch] {type(e).__name__} for {url}")
        return None

    if r.status_code != 200:
        print(f"[fetch] HTTP {r.status_code} for {url}")
        return None

    result = trafilatura.bare_extraction(
        r.content,
        include_comments=False,
        include_tables=True,
    )
    if result is None or not result.text:
        print(f"[fetch] no article extracted from {url}")
        return None

    return (result.title or "").strip(), result.text.strip()
