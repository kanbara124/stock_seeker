"""
Nxny.com (股票报告网) research report collector.
Uses requests for public pages; optional login for authenticated content.
"""

import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://www.nxny.com"
_STOCK_URL = f"{_BASE}/stock/stock_{{ticker}}/"
_LOGIN_URL = f"{_BASE}/user/userlogin.aspx"

_NXNY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_REPORT_URL_RE = re.compile(r"/report/view_(\d+)\.html")

_PAGE_SIZE = 20


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _NXNY_UA
    s.headers["Accept-Language"] = "zh-CN,zh;q=0.9"
    return s


def _login(session: requests.Session) -> bool:
    email = os.environ.get("NXNY_EMAIL", "")
    password = os.environ.get("NXNY_PASSWORD", "")
    if not email or not password:
        return False

    try:
        r = session.get(_LOGIN_URL, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        viewstate = soup.find("input", id="__VIEWSTATE")
        eventvalidation = soup.find("input", id="__EVENTVALIDATION")

        payload = {
            "ctl00$web_center$EmailTxt": email,
            "ctl00$web_center$PassTxt": password,
            "ctl00$web_center$SubMit": "登  录",
        }
        if viewstate:
            payload["__VIEWSTATE"] = viewstate.get("value", "")
        if eventvalidation:
            payload["__EVENTVALIDATION"] = eventvalidation.get("value", "")

        r2 = session.post(_LOGIN_URL, data=payload, timeout=15)
        if email not in r2.url and "userlogin" not in r2.url:
            return True
        return False
    except Exception as exc:
        print(f"[nxny] login failed: {exc}")
        return False


def _fetch_page(url: str, session: requests.Session) -> str | None:
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        r.encoding = "utf-8"
        return r.text
    except Exception as exc:
        print(f"[nxny] fetch failed {url}: {exc}")
        return None


def _parse_report_list(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    for li in soup.select("ul.news-list li"):
        try:
            link = li.select_one("a.rlist")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href:
                continue
            url = urljoin(_BASE, href)

            nr = li.select_one("p.nr")
            meta_text = nr.get_text(strip=True) if nr else ""

            rating = ""
            author = ""
            upload_time = ""
            for part in meta_text.split("&nbsp;&nbsp;&nbsp;&nbsp;"):
                part = part.strip()
                if "评级：" in part:
                    rating = part.split("评级：", 1)[-1].strip()
                elif "作者：" in part:
                    author = part.split("作者：", 1)[-1].strip()
                elif "上传时间：" in part:
                    upload_time = part.split("上传时间：", 1)[-1].strip()

            results.append({
                "title": title[:120],
                "url": url,
                "text": f"【{upload_time}】【评级：{rating}】【作者：{author}】{title}",
                "source": "股票报告网",
            })
        except Exception:
            continue
    return results


def _parse_report_detail(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")

    content = soup.select_one(".report-content, .article-content, #article_content")
    if content:
        text = content.get_text(separator="\n", strip=True)
        return text[:4000] if text else None

    meta_parts = []
    for sel in [".report-info", ".article-info", "td[style*='padding']"]:
        el = soup.select_one(sel)
        if el:
            meta_parts.append(el.get_text(separator=" ", strip=True)[:500])

    body_text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""
    lines = body_text.split("\n")
    content_lines = []
    start_collecting = False
    for line in lines:
        line_s = line.strip()
        if "本报告导读" in line_s or "报告摘要" in line_s or "事件描述" in line_s:
            start_collecting = True
            content_lines.append(line_s)
            continue
        if start_collecting:
            if "风险提示" in line_s or "免责声明" in line_s or "相关报告" in line_s:
                content_lines.append(line_s)
                break
            if len(line_s) > 10:
                content_lines.append(line_s)

    if content_lines:
        return "\n".join(content_lines)[:4000]

    if meta_parts:
        return "\n".join(meta_parts)[:2000]

    title = soup.select_one("h1, h2, .title")
    if title:
        return title.get_text(strip=True)

    return None


def get_nxny_reports(ticker: str, limit: int = 5) -> list[dict[str, str]]:
    session = _make_session()

    logged_in = _login(session)
    if logged_in:
        print("[nxny] logged in successfully")
    else:
        print("[nxny] proceeding without login (public access)")

    url = _STOCK_URL.format(ticker=ticker)
    html = _fetch_page(url, session)
    if not html:
        return []

    reports = _parse_report_list(html)

    page = 2
    while len(reports) < limit * 3:
        page_url = _STOCK_URL.format(ticker=ticker).rstrip("/") + f"_p{page}/"
        page_html = _fetch_page(page_url, session)
        if not page_html:
            break
        more = _parse_report_list(page_html)
        if not more:
            break
        reports.extend(more)
        page += 1

    selected = []
    for r in reports:
        if len(selected) >= limit:
            break
        detail_html = _fetch_page(r["url"], session)
        if detail_html:
            detail_text = _parse_report_detail(detail_html)
            if detail_text:
                r["text"] = f"{r['text']}\n\n{detail_text}"
        selected.append(r)
        time.sleep(0.5)

    return selected
