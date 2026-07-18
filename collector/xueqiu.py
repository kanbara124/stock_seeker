"""
Xueqiu data collector.
- xueqiu_discussions: stock discussion posts via statuses search (T4)
- xueqiu_announcements: annual/semi-annual/quarterly reports (T1)
- xueqiu_hot_posts: popular analysis posts via hot list (T4)

All API calls go through Playwright's browser context to bypass the Alibaba
Cloud WAF.  Logged-in cookies are injected *after* the initial homepage visit
to prevent the server from overwriting them.

Set ``XUEQIU_COOKIE`` in ``.env`` for authenticated access::

    XUEQIU_COOKIE=xq_a_token=...; xq_r_token=...; xq_id_token=...
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from html import unescape as html_unescape
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

_PW_AVAILABLE = False

_XQ_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_XQ_HOMEPAGE = "https://xueqiu.com"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _xueqiu_prefix(ticker: str) -> str:
    if ticker.startswith("6"):
        return "SH"
    if ticker.startswith(("0", "3")):
        return "SZ"
    return "SH"


def _stock_url(ticker: str) -> str:
    return f"https://xueqiu.com/S/{_xueqiu_prefix(ticker)}{ticker}"


def _announcement_url(ticker: str) -> str:
    return f"{_stock_url(ticker)}#/announcement"


def _ensure_playwright():
    global _PW_AVAILABLE
    if not _PW_AVAILABLE:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout  # noqa: F811
            _PW_AVAILABLE = True
        except ImportError:
            raise RuntimeError("playwright 未安装，跳过雪球抓取")
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout  # noqa: F811
    return sync_playwright, PwTimeout


def _parse_env_cookies() -> dict[str, str]:
    raw = os.environ.get("XUEQIU_COOKIE", "")
    cookies: dict[str, str] = {}
    if not raw:
        return cookies
    for pair in raw.split(";"):
        pair = pair.strip().strip('"')
        if "=" in pair:
            k, v = pair.split("=", 1)
            k = k.strip().strip('"')
            v = v.strip().strip('"')
            if k and v:
                cookies[k] = v
    return cookies


def _clean_html(raw: str) -> str:
    """Strip HTML tags and decode entities, return plain text."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "lxml")
    return html_unescape(soup.get_text(separator="\n", strip=True))


def _item_user(item: dict) -> str:
    return (item.get("user") or {}).get("screen_name", "")


def _item_url(item: dict) -> str:
    uid = item.get("user_id", "")
    rid = item.get("id", "")
    target = item.get("target", "")
    if target:
        return f"https://xueqiu.com{target}"
    if uid and rid:
        return f"https://xueqiu.com/{uid}/{rid}"
    return ""


def _item_title(item: dict) -> str:
    t = (item.get("title") or "").strip()
    if t:
        return _clean_html(t)
    t = (item.get("description") or "").strip()
    if t:
        return _clean_html(t)
    text = _clean_html(item.get("text") or "")
    return text[:80].replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# shared browser context (cookie-after-homepage pattern)
# ---------------------------------------------------------------------------


@dataclass
class _XQBrowser:
    browser: Any = None
    context: Any = None
    page: Any = None
    logged_in: bool = False

    def __enter__(self):
        sync_playwright, _ = _ensure_playwright()
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.context = self.browser.new_context(
            user_agent=_XQ_UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        self.page = self.context.new_page()
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        self.page.goto(_XQ_HOMEPAGE, wait_until="domcontentloaded", timeout=30000)
        self.page.wait_for_timeout(3000)

        env_cookies = _parse_env_cookies()
        if env_cookies:
            self.context.add_cookies([
                {"name": k, "value": v, "domain": ".xueqiu.com", "path": "/"}
                for k, v in env_cookies.items()
            ])

        cookies = {c["name"]: c["value"] for c in self.context.cookies()}
        self.logged_in = bool(cookies.get("xq_a_token"))

        return self

    def __exit__(self, *args):
        try:
            if self.browser:
                self.browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def api_navigate(self, url: str, params: dict | None = None) -> dict:
        """Navigate to an API JSON URL and return parsed body."""
        full = url
        if params:
            full = url + "?" + urlencode(params)

        try:
            resp = self.page.goto(full, wait_until="domcontentloaded", timeout=15000)
            if resp and resp.status == 200:
                raw = self.page.evaluate("() => document.body.innerText")
                if raw and raw.strip().startswith("{"):
                    return json.loads(raw)
        except Exception:
            pass
        return {}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

_ANNOUNCEMENT_KEYWORDS = [
    "年报", "年度报告", "半年报", "半年度报告", "一季报",
    "三季报", "第一季度报告", "第三季度报告",
]


def get_xueqiu_discussions(
    ticker: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Fetch stock discussion posts from xueqiu statuses search (T4)."""
    results: list[dict[str, str]] = []
    try:
        with _XQBrowser() as xq:
            symbol = f"{_xueqiu_prefix(ticker)}{ticker}"
            data = xq.api_navigate(
                "https://xueqiu.com/statuses/search.json",
                {"count": limit * 2, "comment": 0, "symbol": symbol,
                 "hl": 0, "source": "all", "sort": "time", "page": 1},
            )
            for item in data.get("list", []):
                if len(results) >= limit:
                    break
                title = _item_title(item)
                text = _clean_html(item.get("text") or item.get("description") or "")
                user = _item_user(item)
                url = _item_url(item)
                if not url:
                    continue
                if not text.strip() and not title.strip():
                    continue
                results.append({
                    "title": f"【雪球用户 {user}】{title}"[:120],
                    "url": url,
                    "text": text[:2000],
                    "source": "雪球讨论",
                })
    except RuntimeError:
        pass
    except Exception as exc:
        print(f"[xueqiu] discussions failed: {exc}")
    return results


def get_xueqiu_announcements(
    ticker: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Fetch financial report announcements from xueqiu (T1 supplementary).

    Tries the rendered announcement sub-page; if blocked (405, headless
    detection), returns empty — the primary T1 source is 巨潮 via akshare.
    """
    results: list[dict[str, str]] = []
    try:
        with _XQBrowser() as xq:
            xq.page.goto(_announcement_url(ticker),
                         wait_until="domcontentloaded", timeout=30000)
            xq.page.wait_for_timeout(5000)
            html = xq.page.content()

            if len(html) > 3000:
                links = xq.page.query_selector_all("a")
                for a in links[: limit * 3]:
                    if len(results) >= limit:
                        break
                    try:
                        title = (a.inner_text()).strip()
                        href = (a.get_attribute("href") or "").strip()
                        if not title or not href:
                            continue
                        if not any(kw in title for kw in _ANNOUNCEMENT_KEYWORDS):
                            continue
                        if href and not href.startswith("http"):
                            href = f"https://xueqiu.com{href}"
                        results.append({
                            "title": title[:120],
                            "url": href,
                            "text": title,
                            "source": "雪球公告",
                        })
                    except Exception:
                        continue
    except RuntimeError:
        pass
    except Exception as exc:
        print(f"[xueqiu] announcements failed: {exc}")
    return results


def get_xueqiu_hot_posts(
    ticker: str,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Get popular/long-form analysis posts from xueqiu hot list (T4)."""
    results: list[dict[str, str]] = []
    try:
        with _XQBrowser() as xq:
            symbol = f"{_xueqiu_prefix(ticker)}{ticker}"
            data = xq.api_navigate(
                "https://xueqiu.com/statuses/hot/list.json",
                {"symbol": symbol, "page": 1, "size": limit},
            )
            for item in data.get("items", [])[:limit]:
                os_ = item.get("original_status", {})
                title = _item_title(os_)
                text = _clean_html(os_.get("text") or os_.get("description") or "")
                user = _item_user(os_)
                url = _item_url(os_)
                if not url:
                    continue
                if not text.strip() and not title.strip():
                    continue
                results.append({
                    "title": f"【雪球用户 {user}】{title}"[:120],
                    "url": url,
                    "text": text[:2000],
                    "source": "雪球深度",
                })
    except RuntimeError:
        pass
    except Exception as exc:
        print(f"[xueqiu] hot posts failed: {exc}")
    return results
