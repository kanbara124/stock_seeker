"""
PDF announcement downloader & text extractor for cninfo (巨潮资讯网).

Constructs the direct PDF URL from announcement metadata:
  http://static.cninfo.com.cn/finalpage/{date}/{announcement_id}.PDF

If the direct URL fails (404), falls back to Playwright rendering the
detail page to find the actual PDF link.
"""

from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, urlparse

import fitz  # pymupdf
import requests

from collector.rate_limit import safe_get

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_PDF_BASE = "http://static.cninfo.com.cn/finalpage"
_STATIC_CNINFO = "http://static.cninfo.com.cn"


def _extract_ann_id(detail_url: str) -> str:
    qs = parse_qs(urlparse(detail_url).query)
    return qs.get("announcementId", [""])[0]


def _build_pdf_url(ann_date: str, ann_id: str) -> str:
    return f"{_PDF_BASE}/{ann_date}/{ann_id}.PDF"


def _try_direct_download(pdf_url: str) -> bytes | None:
    try:
        r = safe_get(pdf_url, headers={"Referer": "http://www.cninfo.com.cn/"})
        if r.status_code == 200 and len(r.content) > 1000:
            ct = r.headers.get("Content-Type", "")
            if "pdf" in ct.lower() or pdf_url.lower().endswith(".pdf"):
                return r.content
    except Exception:
        pass
    return None


def _find_pdf_via_playwright(detail_url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=_UA, viewport={"width": 1920, "height": 1080}
            )
            page = ctx.new_page()
            page.goto(detail_url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(3000)

            links = page.query_selector_all("a[href]")
            for a in links:
                href = (a.get_attribute("href") or "").strip()
                if ".PDF" in href or ".pdf" in href:
                    if href.startswith("/"):
                        href = f"{_STATIC_CNINFO}{href}"
                    elif not href.startswith("http"):
                        href = f"{_STATIC_CNINFO}/{href.lstrip('/')}"
                    browser.close()
                    return href

            browser.close()
    except Exception:
        pass
    return ""


def _download_with_fallback(detail_url: str, ann_date: str) -> bytes | None:
    ann_id = _extract_ann_id(detail_url)
    if not ann_id:
        return None

    pdf_url = _build_pdf_url(ann_date, ann_id)
    content = _try_direct_download(pdf_url)
    if content:
        return content

    fallback_url = _find_pdf_via_playwright(detail_url)
    if fallback_url:
        time.sleep(1)
        content = _try_direct_download(fallback_url)
        if content:
            return content

    return None


def extract_announcement_pdf(detail_url: str, ann_date: str) -> str | None:
    """Download and extract text from a cninfo announcement PDF.

    Args:
        detail_url: cninfo detail page URL (e.g. ...?announcementId=...)
        ann_date: announcement date in YYYY-MM-DD format

    Returns:
        Extracted plain text, or None on failure.
    """
    content = _download_with_fallback(detail_url, ann_date)
    if not content:
        return None

    try:
        doc = fitz.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())
        doc.close()

        combined = "\n\n".join(pages)
        return combined[:4000] if combined else None
    except Exception as exc:
        print(f"[pdf] pymupdf parse failed: {exc}")
        return None
